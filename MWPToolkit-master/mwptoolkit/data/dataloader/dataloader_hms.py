# -*- encoding: utf-8 -*-
# @Author: Yihuai Lan
# @Time: 2022/1/8 14:18
# @File: dataloader_hms.py
# @Update Time: 2022/1/8 14:18
import math

from typing import List

from mwptoolkit.config import Config
from mwptoolkit.data.dataset.dataset_hms import DatasetHMS
from mwptoolkit.data.dataloader.template_dataloader import TemplateDataLoader
from mwptoolkit.utils.enum_type import SpecialTokens,FixType,NumMask


def get_num_mask(num_size_batch, generate_nums):
    num_mask = []
    max_num_size = max(num_size_batch) + len(generate_nums)
    for i in num_size_batch:
        d = i + len(generate_nums)
        num_mask.append([0] * d + [1] * (max_num_size - d))
    return num_mask


class DataLoaderHMS(TemplateDataLoader):
    def __init__(self,config:Config,dataset:DatasetHMS):
        """

        :param config:
        :param dataset:

        expected that config includes these parameters below:

        model (str): model name.

        equation_fix (str): [infix | postfix | prefix], convert equation to specified format.

        train_batch_size (int): the training batch size.

        test_batch_size (int): the testing batch size.

        symbol_for_tree (bool): build output symbols for tree or not.

        share_vocab (bool): encoder and decoder of the model share the same vocabulary, often seen in Seq2Seq models.

        max_len (int|None): max input length.

        max_equ_len (int|None): max output length.

        add_sos (bool): add sos token at the head of input sequence.

        add_eos (bool): add eos token at the tail of input sequence.

        device (torch.device):
        """
        super().__init__(config, dataset)
        self.trainset_nums = len(dataset.trainset)
        self.validset_nums = len(dataset.validset)
        self.testset_nums = len(dataset.testset)

        self.in_pad_token = dataset.in_word2idx[SpecialTokens.PAD_TOKEN]
        self.in_unk_token = dataset.in_word2idx[SpecialTokens.UNK_TOKEN]

        if self.symbol_for_tree or self.equation_fix == FixType.MultiWayTree:
            self.out_pad_token = self.in_pad_token
            self.out_unk_token = dataset.out_symbol2idx[SpecialTokens.UNK_TOKEN]
            self.temp_unk_token = dataset.temp_symbol2idx[SpecialTokens.UNK_TOKEN]

        else:
            if self.share_vocab:
                self.out_pad_token = self.in_pad_token
                self.out_unk_token = self.in_unk_token
                self.temp_pad_token = self.in_pad_token
                self.temp_unk_token = self.in_unk_token
            else:
                self.out_pad_token = dataset.out_symbol2idx[SpecialTokens.PAD_TOKEN]
                self.out_unk_token = dataset.out_symbol2idx[SpecialTokens.UNK_TOKEN]
                self.temp_pad_token = dataset.temp_symbol2idx[SpecialTokens.PAD_TOKEN]
                self.temp_unk_token = dataset.temp_symbol2idx[SpecialTokens.UNK_TOKEN]
        self.__init_batches()

    def __init_batches(self):
        self.trainset_batches = []
        self.validset_batches = []
        self.testset_batches = []
        for set_type in ['train', 'valid', 'test']:
            if set_type == 'train':
                datas = self.dataset.trainset
                batch_size = self.train_batch_size
            elif set_type == 'valid':
                datas = self.dataset.validset
                batch_size = self.test_batch_size
            elif set_type == 'test':
                datas = self.dataset.testset
                batch_size = self.test_batch_size
            else:
                raise ValueError("{} type not in ['train', 'valid', 'test'].".format(type))
            num_total = len(datas)
            batch_num = math.ceil(num_total / batch_size)
            for batch_i in range(batch_num):
                start_idx = batch_i * batch_size
                end_idx = (batch_i + 1) * batch_size
                if end_idx <= num_total:
                    batch_data = datas[start_idx:end_idx]
                else:
                    batch_data = datas[start_idx:num_total]
                built_batch = self.__build_batch(batch_data)
                if set_type == 'train':
                    self.trainset_batches.append(built_batch)
                elif set_type == 'valid':
                    self.validset_batches.append(built_batch)
                elif set_type == 'test':
                    self.testset_batches.append(built_batch)
                else:
                    raise ValueError("{} type not in ['train', 'valid', 'test'].".format(type))
        self.__trainset_batch_idx = -1
        self.__validset_batch_idx = -1
        self.__testset_batch_idx = -1
        self.trainset_batch_nums = len(self.trainset_batches)
        self.validset_batch_nums = len(self.validset_batches)
        self.testset_batch_nums = len(self.testset_batches)

    def __build_batch(self,batch_data):
        ques_batch = []
        equ_batch = []
        temp_batch = []
        ques_source_batch = []
        equ_source_batch = []
        temp_source_batch = []
        ques_source_1_batch = []
        infix_equ_batch = []

        num_list_batch = []
        num_pos_batch = []

        id_batch = []
        ans_batch = []

        equ_len_batch = []
        ques_len_batch = []

        num_stack_batch = []

        group_nums_batch = []

        for data in batch_data:
            sentence = data["question"]
            equation = data["equation"]
            template = data["template"]

            # question word to index
            if self.add_sos:
                sentence = [SpecialTokens.SOS_TOKEN] + sentence
            if self.add_eos:
                sentence = sentence + [SpecialTokens.EOS_TOKEN]
            ques_tensor = self._word2idx(sentence)

            # equation symbol to index
            equ_tensor = self._equ_symbol2idx(equation)
            temp_tensor = self._temp_symbol2idx(template)
            if self.symbol_for_tree or self.equation_fix == FixType.MultiWayTree:
                pass
            else:
                if self.share_vocab:
                    equ_tensor.append(self.dataset.in_word2idx[SpecialTokens.EOS_TOKEN])
                    temp_tensor.append(self.dataset.in_word2idx[SpecialTokens.EOS_TOKEN])
                else:
                    equ_tensor.append(self.dataset.out_symbol2idx[SpecialTokens.EOS_TOKEN])
                    temp_tensor.append(self.dataset.temp_symbol2idx[SpecialTokens.EOS_TOKEN])

            equ_len_batch.append(len(equ_tensor))
            ques_len_batch.append(len(ques_tensor))
            ques_batch.append(ques_tensor)
            equ_batch.append(equ_tensor)
            temp_batch.append(temp_tensor)

            # question / equation to string
            ques_source = ' '.join(sentence)
            if self.equation_fix == FixType.MultiWayTree:
                equ_source = ' '
                temp_source = ' '
            else:
                equ_source = ' '.join(equation)
                temp_source = ' '.join(template)
            ques_source_batch.append(ques_source)
            equ_source_batch.append(equ_source)
            temp_source_batch.append(temp_source)
            ques_source_1_batch.append(data["ques source 1"])
            # infix equation
            infix_equ_batch.append(data["infix equation"])
            # quantity list
            num_list_batch.append(data["number list"])
            # quantity position
            if self.add_sos:
                num_pos = [pos + 1 for pos in
                           data["number position"]]  # pos plus one because of adding <SOS> at the head of sentence
            else:
                num_pos = [pos for pos in data["number position"]]
            num_pos_batch.append(num_pos)
            # question id and answer
            id_batch.append(data["id"])
            ans_batch.append(data["ans"])
            try:
                group_nums_batch.append(data["group nums"])
            except:
                group_nums_batch.append([])

            num_stack_batch.append(self._build_num_stack(equation, data["number list"]))

        # padding batch question
        ques_batch = self._pad_input_batch(ques_batch, ques_len_batch)
        # padding batch equation
        if self.equation_fix == FixType.MultiWayTree:
            pass
        else:
            equ_batch = self._pad_output_batch(equ_batch, equ_len_batch)
            temp_batch = self._pad_output_batch(temp_batch, equ_len_batch)

        if self.max_len is not None:
            ques_len_batch = [self.max_len if l > self.max_len else l for l in ques_len_batch]

        # question mask
        ques_mask_batch = self._get_mask(ques_len_batch)
        # equation mask
        equ_mask_batch = self._get_mask(equ_len_batch)
        # quantity count
        num_size_batch = [len(num_pos) for num_pos in num_pos_batch]
        # quantity mask
        num_mask_batch = get_num_mask(num_size_batch, self.dataset.generate_list)

        new_group_nums_batch = []
        for group_nums in group_nums_batch:
            new_group_nums = []
            for group_num in group_nums:
                new_group_num = []
                for pos in group_num:
                    if self.add_sos:
                        new_group_num.append(pos + 1)
                    else:
                        new_group_num.append(pos)
                new_group_nums.append(new_group_num)
            new_group_nums_batch.append(new_group_nums)
        pad_num_pos = [-1] * len(self.dataset.out_idx2symbol)
        max_span_nums = 0
        span_nums_batch = []
        spans_batch = []
        spans_length_batch = []
        trees_batch = []
        span_num_pos_batch = []
        word_num_poses_batch = []
        word_num_poses_pad_batch = []
        for data in batch_data:
            span_nums = len(data['split sentences'])
            span_nums_batch.append(span_nums)
            span_num_pos = [-1] * len(self.dataset.out_idx2symbol)
            word_num_poses = [[-1] * len(self.dataset.out_idx2symbol) for _ in range(span_nums)]
            for i, span in enumerate(data['split sentences']):
                for j, word in enumerate(span):
                    if word in NumMask.number and word in self.dataset.out_idx2symbol:
                        class_index = self.dataset.out_symbol2idx[word]
                        span_num_pos[class_index] = i
                        word_num_poses[i][class_index] = j
            span_num_pos_batch.append(span_num_pos)
            word_num_poses_batch.append(word_num_poses)
        max_span_nums = max(span_nums_batch)
        for span_idx in range(max_span_nums):
            span_i_batch = []
            span_i_length_batch = []
            tree_i_batch = []
            word_num_poses_pad = []
            for b_i, data in enumerate(batch_data):
                if span_idx >= span_nums_batch[b_i]:
                    span_i_batch.append([])
                    span_i_length_batch.append(0)
                    word_num_poses_pad.append(pad_num_pos)
                else:
                    sentence = data['split sentences'][span_idx]
                    sentence_idx = self._word2idx(sentence)
                    span_i_length = len(sentence_idx)
                    span_i_batch.append(sentence_idx)
                    span_i_length_batch.append(span_i_length)
                    word_num_poses_pad.append(word_num_poses_batch[b_i][span_idx])
                try:
                    tree = data['deprel tree'][span_idx]
                    tree_i_batch.append(tree)
                except:
                    tree_i_batch.append(None)
            span_i_batch = self._pad_input_batch(span_i_batch, span_i_length_batch)
            spans_batch.append(span_i_batch)
            spans_length_batch.append(span_i_length_batch)
            trees_batch.append(tree_i_batch)
            word_num_poses_pad_batch.append(word_num_poses_pad)

        return {
            "spans": spans_batch,
            "spans len": spans_length_batch,
            "span nums": span_nums_batch,
            "deprel tree": trees_batch,
            "span num pos": span_num_pos_batch,
            "word num poses": word_num_poses_batch,
            "question": ques_batch,
            "equation": equ_batch,
            "template": temp_batch,
            "ques len": ques_len_batch,
            "equ len": equ_len_batch,
            "num list": num_list_batch,
            "num pos": num_pos_batch,
            "id": id_batch,
            "num mask": num_mask_batch,
            "ques mask": ques_mask_batch,
            "equ mask": equ_mask_batch,
            "num stack": num_stack_batch,
            "ans": ans_batch,
            "num size": num_size_batch,
            "ques_source": ques_source_batch,
            "equ_source": equ_source_batch,
            "temp_source": temp_source_batch,
            "ques source 1": ques_source_1_batch,
            "group nums": new_group_nums_batch,
            "infix equation": infix_equ_batch,
        }

    def build_batch_for_predict(self, batch_data: List[dict]):
        for idx, data in enumerate(batch_data):
            data['equation'] = []
            data['template'] = []
            data['infix equation'] = []
            data['ans'] = None
            if data.get('id', None) is None:
                data['id'] = 'temp_{}'.format(idx)
        batch = self.__build_batch(batch_data)
        del batch['equation']
        del batch['template']
        del batch['equ len']
        del batch['equ mask']
        del batch['ans']
        del batch['equ_source']
        del batch['temp_source']
        del batch['infix equation']

        return batch
