The idea of the project was to train a GPT-2 model to solve tough math word problems.

The data taken is the GSM8K dataset. 
This dataset contains 8.5K school math problems. The dataset is designed in such a way that only basic arithmetic calculations are needed to solve the problem.
This dataset was carefully constructed by OpenAI to encounter the possibility of LLM’s using shallow heuristics to get accuracy. This dataset can be found at [https://github.com/openai/grade-school-math](https://github.com/openai/grade-school-math).

MWPToolkit folder taken from [https://github.com/LYH-YF/MWPToolkit](https://github.com/LYH-YF/MWPToolkit) with a few tweaks. This was used to test the GSM8K questions using a MWP-Bert model for comparison.

The model was trained in a linear LR scheduler and Adam Optimizer. The number of epochs is a hyperparameter that can be tuned.  The output will be saved in the model folder.

The plan is to see if the self consistency method improves the results of a GPT2 model.
