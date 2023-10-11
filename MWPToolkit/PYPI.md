# MWPToolkit
MWPToolkit is a PyTorch-based toolkit for Math Word Problem(MWP) solving. It is a comprehensive framework for research purpose that integrates popular MWP benchmark datasets and typical deep learning-based MWP algorithms. 

## Feature

* **Comprehensive toolkit for MWP solving task**. To our best knowledge, MWP toolkit is the first open-source library for MWP solving task, where popular benchmark datasets and advanced deep learning-based methods for MWP solving tasks are integrated into a unified framework. 
* **Easy to get started**. MWP toolkit is developed upon Python and Pytorch. We provide detailed instruction, which facilitates users to evaluate the build-in datasets or apply the code to their own data.
* **Highly modularized framework**. MWP toolkit is designed with highly reused modules and provides convenient interfaces for users. Specifically, data preprocessor, data loader, encoder, decoder and evaluator form the running procedure. Each module could be developed and extended independently.

## News in version 0.0.6

* 1.Fix some bugs [Issue [#12](https://github.com/LYH-YF/MWPToolkit/issues/12), [#8](https://github.com/LYH-YF/MWPToolkit/issues/8)]:

  (1)**from_prefix_to_infix**,**from_postfix_to_infix** in mwptoolkit/utils/preprocess_tool/equation_operator.py

  (2)the sequence length will be longer than pos_embedder's max length in **RobertGen**, **BertGen**.
  
  (3)data preprocessing for new dataset won't **automatically remove 'x=' or '=x'** in single equation.

* 2.Update new models:

  (1)Seq2Tree model [**BertTD**](https://arxiv.org/abs/2110.08464)

  (2)Seq2Tree model [**MWPBert**](https://arxiv.org/abs/2107.13435)
* 3.Rewrite Dataloader and Config

* 4.Implement function save_dataset() and load_from_pretrained() of Dataset

* 5.Implement function save_config() and load_from_pretrained() of Config
