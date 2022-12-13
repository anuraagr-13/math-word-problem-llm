import torch as th
from dataset import get_examples, GSMDataset, extract_answer, is_correct
from calculator import sample
from transformers import GPT2Tokenizer, GPT2LMHeadModel


def main():
    device = th.device("cuda")
    tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
    model = GPT2LMHeadModel.from_pretrained("model_ckpts")
    model.to(device)
    print("Model Loaded")
    test_examples = get_examples("test")
    count = 0

    for j in range(4):
        vals = []
        for i in range(70):
            qn = test_examples[j]["question"]
            print(qn)
            sample_len = 130

            val = sample(model, qn, tokenizer, device, sample_len)
            print('Extracted Answer', extract_answer(val))
            print('Actual Answer',  extract_answer(test_examples[j]['answer']))
            if(extract_answer(val) != '[invalid]'):
                vals.append(extract_answer(val))
        occ = {ia: vals.count(ia) for ia in vals}
        print(occ)
        max_value = max(occ, key = occ.get)
        print(max_value)
        if(is_correct(max_value, test_examples[i])):
            print("This is right")
        #accuracy = count/100
        #print('Accuracy', accuracy)


if __name__ == "__main__":
    main()
