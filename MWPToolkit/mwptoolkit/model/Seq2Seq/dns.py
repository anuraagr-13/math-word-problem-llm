# -*- encoding: utf-8 -*-
# @Author: Yihuai Lan
# @Time: 2021/08/21 04:35:13
# @File: dns.py

import copy
import random
from typing import Tuple, Dict, Any

import torch
from torch import nn
from torch.nn import functional as F

from mwptoolkit.module.Encoder.rnn_encoder import BasicRNNEncoder
from mwptoolkit.module.Decoder.rnn_decoder import BasicRNNDecoder, AttentionalRNNDecoder
from mwptoolkit.module.Embedder.basic_embedder import BasicEmbedder
from mwptoolkit.loss.nll_loss import NLLLoss
from mwptoolkit.utils.enum_type import NumMask, SpecialTokens


class DNS(nn.Module):
    """
    Reference:
        Wang et al. "Deep Neural Solver for Math Word Problems" in EMNLP 2017.
    """
    def __init__(self, config, dataset):
        super(DNS, self).__init__()
        self.device = config["device"]
        self.embedding_size = config['embedding_size']
        self.bidirectional = config["bidirectional"]
        self.hidden_size = config["hidden_size"]
        self.decode_hidden_size = config["decode_hidden_size"]
        self.encoder_rnn_cell_type = config["encoder_rnn_cell_type"]
        self.decoder_rnn_cell_type = config["decoder_rnn_cell_type"]
        self.dropout_ratio = config["dropout_ratio"]
        self.num_layers = config["num_layers"]
        self.attention = config["attention"]
        self.share_vocab = config["share_vocab"]
        self.max_gen_len = config["max_output_len"]
        self.teacher_force_ratio = config['teacher_force_ratio']

        self.num_start = dataset.num_start
        self.vocab_size = len(dataset.in_idx2word)
        self.symbol_size = len(dataset.out_idx2symbol)
        self.mask_list = NumMask.number

        if config["share_vocab"]:
            self.out_symbol2idx = dataset.out_symbol2idx
            self.out_idx2symbol = dataset.out_idx2symbol
            self.in_word2idx = dataset.in_word2idx
            self.in_idx2word = dataset.in_idx2word
            self.sos_token_idx = self.in_word2idx[SpecialTokens.SOS_TOKEN]
        else:
            self.out_symbol2idx = dataset.out_symbol2idx
            self.out_idx2symbol = dataset.out_idx2symbol
            self.sos_token_idx = self.out_symbol2idx[SpecialTokens.SOS_TOKEN]

        try:
            self.out_sos_token = self.out_symbol2idx[SpecialTokens.SOS_TOKEN]
        except:
            self.out_sos_token = None
        try:
            self.out_eos_token = self.out_symbol2idx[SpecialTokens.EOS_TOKEN]
        except:
            self.out_eos_token = None
        try:
            self.out_pad_token = self.out_symbol2idx[SpecialTokens.PAD_TOKEN]
        except:
            self.out_pad_token = None

        self.in_embedder = BasicEmbedder(self.vocab_size, self.embedding_size, self.dropout_ratio)
        if self.share_vocab:
            self.out_embedder = self.in_embedder
        else:
            self.out_embedder = BasicEmbedder(self.symbol_size, self.embedding_size, self.dropout_ratio)

        self.encoder=BasicRNNEncoder(self.embedding_size,self.hidden_size,self.num_layers,\
                                        self.encoder_rnn_cell_type,self.dropout_ratio,self.bidirectional)
        if self.attention:
            self.decoder=AttentionalRNNDecoder(self.embedding_size,self.decode_hidden_size,self.hidden_size,\
                                                self.num_layers,self.decoder_rnn_cell_type,self.dropout_ratio)
        else:
            self.decoder=BasicRNNDecoder(self.embedding_size,self.decode_hidden_size,self.num_layers,\
                                        self.decoder_rnn_cell_type,self.dropout_ratio)

        self.dropout = nn.Dropout(self.dropout_ratio)
        self.generate_linear = nn.Linear(self.hidden_size, self.symbol_size)

        weight = torch.ones(self.symbol_size).to(self.device)
        pad = self.out_pad_token
        self.loss = NLLLoss(weight, pad)

    def forward(self, seq, seq_length, target=None, output_all_layers=False) -> Tuple[
            torch.Tensor, torch.Tensor, Dict[str, Any]]:
        """

        :param torch.Tensor seq: input sequence, shape: [batch_size, seq_length].
        :param torch.Tensor seq_length: the length of sequence, shape: [batch_size].
        :param torch.Tensor | None target: target, shape: [batch_size, target_length], default None.
        :param bool output_all_layers: return output of all layers if output_all_layers is True, default False.
        :return : token_logits:[batch_size, output_length, output_size], symbol_outputs:[batch_size,output_length], model_all_outputs.
        :rtype: tuple(torch.Tensor, torch.Tensor, dict)
        """
        batch_size = seq.size(0)
        device = seq.device

        seq_emb = self.in_embedder(seq)
        encoder_outputs, encoder_hidden, encoder_layer_outputs = self.encoder_forward(seq_emb, seq_length,
                                                                                      output_all_layers)

        decoder_inputs = self.init_decoder_inputs(target, device, batch_size)

        token_logits, symbol_outputs, decoder_layer_outputs = self.decoder_forward(encoder_outputs, encoder_hidden,
                                                                                   decoder_inputs, target,
                                                                                   output_all_layers)

        model_all_outputs = {}
        if output_all_layers:
            model_all_outputs['inputs_embedding'] = seq_emb
            model_all_outputs.update(encoder_layer_outputs)
            model_all_outputs.update(decoder_layer_outputs)

        return token_logits, symbol_outputs, model_all_outputs

    def calculate_loss(self, batch_data:dict) -> float:
        """Finish forward-propagating, calculating loss and back-propagation.

        :param batch_data: one batch data.
        :return: loss value.

        batch_data should include keywords 'question', 'ques len' and 'equation'
        """
        seq = torch.tensor(batch_data['question']).to(self.device)
        seq_length = torch.tensor(batch_data['ques len']).long()
        target = torch.tensor(batch_data['equation']).to(self.device)

        token_logits, _, _ = self.forward(seq, seq_length, target)
        if self.share_vocab:
            target = self.convert_in_idx_2_out_idx(target)

        outputs = torch.nn.functional.log_softmax(token_logits, dim=-1)
        self.loss.reset()
        self.loss.eval_batch(outputs.view(-1,outputs.size(-1)), target.view(-1))
        self.loss.backward()

        return self.loss.get_loss()

    def model_test(self, batch_data:dict) -> tuple:
        """Model test.

        :param batch_data: one batch data.
        :return: predicted equation, target equation.

        batch_data should include keywords 'question', 'ques len', 'equation' and 'num list'.
        """
        seq = torch.tensor(batch_data['question']).to(self.device)
        seq_length = torch.tensor(batch_data['ques len']).long()
        num_list = batch_data['num list']
        target = torch.tensor(batch_data['equation']).to(self.device)

        _, symbol_outputs, _ = self.forward(seq, seq_length)
        if self.share_vocab:
            target = self.convert_in_idx_2_out_idx(target)
        all_outputs = self.convert_idx2symbol(symbol_outputs, num_list)
        targets = self.convert_idx2symbol(target, num_list)
        return all_outputs, targets

    def predict(self,batch_data:dict,output_all_layers=False):
        """
        predict samples without target.
        :param dict batch_data: one batch data.
        :param bool output_all_layers: return all layer outputs of model.
        :return: token_logits, symbol_outputs, all_layer_outputs
        """
        seq = torch.tensor(batch_data['question']).to(self.device)
        seq_length = torch.tensor(batch_data['ques len']).long()
        token_logits, symbol_outputs, model_all_outputs = self.forward(seq,seq_length,output_all_layers=output_all_layers)
        return token_logits, symbol_outputs, model_all_outputs

    def encoder_forward(self, seq_emb, seq_length, output_all_layers=False):
        encoder_outputs, encoder_hidden = self.encoder(seq_emb, seq_length)

        if self.bidirectional:
            encoder_outputs = encoder_outputs[:, :, self.hidden_size:] + encoder_outputs[:, :, :self.hidden_size]
            if self.encoder_rnn_cell_type == 'lstm':
                encoder_hidden = (encoder_hidden[0][::2].contiguous(), encoder_hidden[1][::2].contiguous())
            else:
                encoder_hidden = encoder_hidden[::2].contiguous()
        if self.encoder.rnn_cell_type == self.decoder.rnn_cell_type:
            pass
        elif (self.encoder.rnn_cell_type == 'gru') and (self.decoder.rnn_cell_type == 'lstm'):
            encoder_hidden = (encoder_hidden, encoder_hidden)
        elif (self.encoder.rnn_cell_type == 'rnn') and (self.decoder.rnn_cell_type == 'lstm'):
            encoder_hidden = (encoder_hidden, encoder_hidden)
        elif (self.encoder.rnn_cell_type == 'lstm') and (
                self.decoder.rnn_cell_type == 'gru' or self.decoder.rnn_cell_type == 'rnn'):
            encoder_hidden = encoder_hidden[0]
        else:
            pass

        all_layer_outputs = {}
        if output_all_layers:
            all_layer_outputs['encoder_outputs'] = encoder_outputs
            all_layer_outputs['encoder_hidden'] = encoder_hidden
        return encoder_outputs, encoder_hidden, all_layer_outputs

    def decoder_forward(self, encoder_outputs, encoder_hidden, decoder_inputs, target=None, output_all_layers=False):
        with_t = random.random()
        seq_len = decoder_inputs.size(1) if target is not None else self.max_gen_len
        decoder_hidden = encoder_hidden
        decoder_input = decoder_inputs[:, 0, :].unsqueeze(1)
        decoder_outputs = []
        token_logits = []
        outputs = []
        output = []
        for idx in range(seq_len):
            if target is not None and with_t < self.teacher_force_ratio:
                decoder_input = decoder_inputs[:, idx, :].unsqueeze(1)
            if self.attention:
                decoder_output, decoder_hidden = self.decoder(decoder_input, decoder_hidden, encoder_outputs)
            else:
                decoder_output, decoder_hidden = self.decoder(decoder_input, decoder_hidden)
            step_output = decoder_output.squeeze(1)
            token_logit = self.generate_linear(step_output)
            output = self.rule_filter_(output, token_logit)
            decoder_outputs.append(decoder_output)
            token_logits.append(token_logit)
            outputs.append(output)

            if self.share_vocab:
                output_ = self.convert_out_idx_2_in_idx(output)
                decoder_input = self.out_embedder(output_)
            else:
                decoder_input = self.out_embedder(output)
        decoder_outputs = torch.stack(decoder_outputs, dim=1)
        token_logits = torch.stack(token_logits, dim=1)
        outputs = torch.stack(outputs,dim=1)
        all_layer_outputs = {}
        if output_all_layers:
            all_layer_outputs['decoder_outputs'] = decoder_outputs
            all_layer_outputs['token_logits'] = token_logits
            all_layer_outputs['outputs'] = outputs
        return token_logits, outputs, all_layer_outputs

    def init_decoder_inputs(self, target, device, batch_size):
        pad_var = torch.LongTensor([self.sos_token_idx] * batch_size).to(device).view(batch_size, 1)
        if target != None:
            decoder_inputs = torch.cat((pad_var, target), dim=1)[:, :-1]
        else:
            decoder_inputs = pad_var
        decoder_inputs = self.out_embedder(decoder_inputs)
        return decoder_inputs

    def decode(self, output):
        device = output.device

        batch_size = output.size(0)
        decoded_output = []
        for idx in range(batch_size):
            decoded_output.append(self.in_word2idx[self.out_idx2symbol[output[idx]]])
        decoded_output = torch.tensor(decoded_output).to(device).view(batch_size, -1)
        return output

    def rule1_filter(self):
        r"""if r_t−1 in {+, −, ∗, /}, then rt will not in {+, −, ∗, /,), =}.
        """
        filters = []
        filters.append(self.out_symbol2idx['+'])
        filters.append(self.out_symbol2idx['-'])
        filters.append(self.out_symbol2idx['*'])
        filters.append(self.out_symbol2idx['/'])
        filters.append(self.out_symbol2idx['^'])
        try:
            filters.append(self.out_symbol2idx[')'])
        except:
            pass
        try:
            filters.append(self.out_symbol2idx['='])
        except:
            pass
        filters.append(self.out_symbol2idx['<EOS>'])
        return torch.tensor(filters).long()

    def rule2_filter(self):
        r"""if r_t-1 is a number, then r_t will not be a number and not in {(, =)}.
        """
        filters = []
        try:
            filters.append(self.out_symbol2idx['('])
        except:
            pass
        # try:
        #     filters.append(self.out_symbol2idx['='])
        # except:
        #     pass
        for idx in range(self.num_start, len(self.out_idx2symbol)):
            filters.append(idx)
        return torch.tensor(filters).long()

    def rule3_filter(self):
        r"""if rt−1 is '=', then rt will not in {+, −, ∗, /, =,)}.
        """
        filters = []
        filters.append(self.out_symbol2idx['+'])
        filters.append(self.out_symbol2idx['-'])
        filters.append(self.out_symbol2idx['*'])
        filters.append(self.out_symbol2idx['/'])
        filters.append(self.out_symbol2idx['^'])
        try:
            filters.append(self.out_symbol2idx['='])
        except:
            pass
        try:
            filters.append(self.out_symbol2idx[')'])
        except:
            pass
        return torch.tensor(filters).long()

    def rule4_filter(self):
        r"""if r_t-1 is '(' , then r_t will not in {(,), +, -, *, /, =}).
        """
        filters = []
        # try:
        #     filters.append(self.out_symbol2idx['('])
        # except:
        #     pass
        try:
            filters.append(self.out_symbol2idx[')'])
        except:
            pass
        try:
            filters.append(self.out_symbol2idx['='])
        except:
            pass
        filters.append(self.out_symbol2idx['+'])
        filters.append(self.out_symbol2idx['-'])
        filters.append(self.out_symbol2idx['*'])
        filters.append(self.out_symbol2idx['/'])
        filters.append(self.out_symbol2idx['^'])
        filters.append(self.out_symbol2idx['<EOS>'])
        return torch.tensor(filters).long()

    def rule5_filter(self):
        r"""if r_t−1 is ')', then r_t will not be a number and not in {(,)};
        """
        filters = []
        try:
            filters.append(self.out_symbol2idx['('])
        except:
            pass
        # try:
        #     filters.append(self.out_symbol2idx[')'])
        # except:
        #     pass
        for idx in range(self.num_start, len(self.out_idx2symbol)):
            filters.append(idx)
        return torch.tensor(filters).long()

    def filter_op(self):
        filters = []
        filters.append(self.out_symbol2idx['+'])
        filters.append(self.out_symbol2idx['-'])
        filters.append(self.out_symbol2idx['*'])
        filters.append(self.out_symbol2idx['/'])
        filters.append(self.out_symbol2idx['^'])
        return torch.tensor(filters).long()

    def filter_END(self):
        filters = []
        filters.append(self.out_symbol2idx['<EOS>'])
        return torch.tensor(filters).long()

    def rule_filter_(self, symbols, token_logit):
        """
        Args:
            symbols (torch.Tensor): [batch_size]
            token_logit (torch.Tensor): [batch_size, symbol_size]
        return:
            symbols of next step (torch.Tensor): [batch_size]
        """
        device = token_logit.device
        next_symbols = []
        current_logit = token_logit.clone().detach()
        if symbols == []:
            filters = torch.cat([self.filter_op(), self.filter_END()])
            for b in range(current_logit.size(0)):
                current_logit[b][filters] = -float('inf')
        else:
            for b, symbol in enumerate(symbols.split(1)):
                if self.out_idx2symbol[symbol] in ['+', '-', '*', '/', '^']:
                    filters = self.rule1_filter()
                    current_logit[b][filters] = -float('inf')
                elif symbol >= self.num_start:
                    filters = self.rule2_filter()
                    current_logit[b][filters] = -float('inf')
                elif self.out_idx2symbol[symbol] in ['=']:
                    filters = self.rule3_filter()
                    current_logit[b][filters] = -float('inf')
                elif self.out_idx2symbol[symbol] in ['(']:
                    filters = self.rule4_filter()
                    current_logit[b][filters] = -float('inf')
                elif self.out_idx2symbol[symbol] in [')']:
                    filters = self.rule5_filter()
                    current_logit[b][filters] = -float('inf')
        next_symbols = current_logit.topk(1, dim=1)[1]
        return next_symbols

    def convert_out_idx_2_in_idx(self, output):
        device = output.device

        batch_size = output.size(0)
        seq_len = output.size(1)

        decoded_output = []
        for b_i in range(batch_size):
            output_i = []
            for s_i in range(seq_len):
                output_i.append(self.in_word2idx[self.out_idx2symbol[output[b_i, s_i]]])
            decoded_output.append(output_i)
        decoded_output = torch.tensor(decoded_output).to(device).view(batch_size, -1)
        return decoded_output

    def convert_in_idx_2_out_idx(self, output):
        device = output.device

        batch_size = output.size(0)
        seq_len = output.size(1)

        decoded_output = []
        for b_i in range(batch_size):
            output_i = []
            for s_i in range(seq_len):
                output_i.append(self.out_symbol2idx[self.in_idx2word[output[b_i, s_i]]])
            decoded_output.append(output_i)
        decoded_output = torch.tensor(decoded_output).to(device).view(batch_size, -1)
        return decoded_output

    def convert_idx2symbol(self, output, num_list):
        batch_size = output.size(0)
        seq_len = output.size(1)
        output_list = []
        for b_i in range(batch_size):
            num_len = len(num_list[b_i])
            res = []
            for s_i in range(seq_len):
                idx = output[b_i][s_i]
                if idx in [self.out_sos_token, self.out_eos_token, self.out_pad_token]:
                    break
                symbol = self.out_idx2symbol[idx]
                if "NUM" in symbol:
                    num_idx = self.mask_list.index(symbol)
                    if num_idx >= num_len:
                        res.append(symbol)
                    else:
                        res.append(num_list[b_i][num_idx])
                else:
                    res.append(symbol)
            output_list.append(res)
        return output_list

    def __str__(self) -> str:
        info = super().__str__()
        total = sum(p.numel() for p in self.parameters())
        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        parameters = "\ntotal parameters : {} \ntrainable parameters : {}".format(total, trainable)
        return info + parameters
