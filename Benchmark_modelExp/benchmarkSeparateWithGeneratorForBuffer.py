'''
A separate script to run the benchmark models to compare with the CLS results

'''
from Benchmark_GenerativeModel import ModelLWF,ModelEWC,ModelSI,ModelJoint,ModelNaive
from avalanche.training import EWC
from avalanche.training import LwF
from avalanche.training import SynapticIntelligence
from avalanche.training import Naive
import numpy as np
import matplotlib.pyplot as plt
import torch
import torchvision
from torch.nn import CrossEntropyLoss
from torch.optim import Adam
from torch.optim import SGD
from avalanche.logging import InteractiveLogger, TextLogger, TensorboardLogger
from avalanche.benchmarks.datasets import MNIST, FashionMNIST, KMNIST, EMNIST, \
QMNIST, FakeData, CocoCaptions, CocoDetection, LSUN, ImageNet, CIFAR10, \
CIFAR100, STL10, SVHN, PhotoTour, SBU, Flickr8k, Flickr30k, VOCDetection, \
VOCSegmentation, Cityscapes, SBDataset, USPS, HMDB51, UCF101, \
CelebA, CORe50Dataset, TinyImagenet, CUB200, OpenLORIS
from avalanche.evaluation.metrics import forgetting_metrics, accuracy_metrics,\
    loss_metrics, timing_metrics, cpu_usage_metrics, StreamConfusionMatrix,\
    disk_usage_metrics, gpu_usage_metrics
from avalanche.training.plugins import EvaluationPlugin,ReplayPlugin,EWCPlugin,SynapticIntelligencePlugin,LwFPlugin
from avalanche.benchmarks.generators import nc_benchmark, ni_benchmark
from torchvision.transforms import Compose, ToTensor, Normalize, RandomCrop
from torch.utils.data import DataLoader, Subset
from sklearn.model_selection import train_test_split
from avalanche.benchmarks.utils import AvalancheDataset
from torchvision import transforms
import pandas as pd
from vae_model import VAE
from vae_training import Vae_Cls_Generator
from utils import utility_funcs,JointTraining,CustomDatasetForDataLoader

def normalizer(data):
    zeroOneRange = ((data-data.min())/(data.max()-data.min()))
    minusOneOneRange = (zeroOneRange - 0.5)/0.5
    return minusOneOneRange

def main():

    benchResultArrayEWC=[]
    benchResultArrayLWF=[]
    benchResultArraySI = []
    benchResultArrayNaive = []
    benchResultArrayJoint = []

    num_runs=3
    n_classes=15
    epochs = 250
    joint_epochs = 2000
    n_experiences=5
    device = "cuda"

    train_batch_size = 16
    eval_batch_size = 16
    joint_batchSize = 32
    patienceJoint = 150

    ewc_lambda_si = 4500#8100
    ewc_lambda = 100
    temperature = 14
    alpha = 7

    learning_rate = 1e-4 #1e-4
    learning_ratejoint = 1e-4
    ##Hyperparameters Generator
    learning_rateGR = 1e-4
    batch_sizeGR = 16
    num_epochsGR = 110
    patienceGR = 70  # No patience

    input_featureDim = 600
    latent_embedding = 100

    num_syntheticExamplesPerDigit = 10#80
    num_originalExamplesPerDigit = 5
    

    tactileData = pd.read_csv("../BP_SensorData.csv")
    labels = ['cube', 'ball', 'airpod_case', 'stapler', 'usb_connector', 'bottle_cap', 'bottle', 
              'solid_cylinder', 'fevistick','smart_watch', 'rubiks_cube', 'airpods', 'rfid_card', 
              'rectangular_cuboid', 'hollow_cylinder'] ### ---> Dummy encoded to integers
    modifiedData = []
    modifiedLabels = []
    
    for i in range(len(labels)):
        dataToTransform = np.array(tactileData.loc[tactileData['object'] == labels[i], ['SensorVal1', 'SensorVal2', 'SensorVal3', 'SensorVal4']])
        for j in range(0,dataToTransform.shape[0],150):
            tempTrans = dataToTransform[j:j+150].reshape(1,-1)
            modifiedLabels.append(i)
            modifiedData.append(tempTrans)
        print("All transformations DONE!!!")

    modifiedLabels = np.array(modifiedLabels)
    modifiedData = np.array(modifiedData).squeeze(1)

    train_indices, val_indices, _, _ = train_test_split(range(len(modifiedLabels)),modifiedLabels,stratify=modifiedLabels,
            test_size=0.20)
    trainData = modifiedData[train_indices]
    trainLabels = modifiedLabels[train_indices]

    testData = modifiedData[val_indices]
    testLabels = modifiedLabels[val_indices]

    X_normalizedTrain = normalizer(trainData)
    X_normalizedTest = normalizer(testData)
    X_normalizedTrain = X_normalizedTrain.astype("float32")
    X_normalizedTest = X_normalizedTest.astype("float32")

    trainData = CustomDatasetForDataLoader(data=X_normalizedTrain,targets=trainLabels)
    testData = CustomDatasetForDataLoader(data=X_normalizedTest,targets=testLabels)
    scenarioTrainVal = nc_benchmark(trainData, testData, n_experiences=5, shuffle=False, seed=9, task_labels=False)

    train_stream = scenarioTrainVal.train_stream
    test_stream =  scenarioTrainVal.test_stream

    interactive_logger = InteractiveLogger()
    modellwf = ModelLWF(input_dim=input_featureDim, output_dim=n_classes)
    modelewc = ModelEWC(input_dim=input_featureDim, output_dim=n_classes)
    modelsi = ModelSI(input_dim=input_featureDim, output_dim=n_classes)
    modelJoint = ModelJoint(input_dim=input_featureDim, output_dim=n_classes)
    modelNaive = ModelNaive(input_dim=input_featureDim, output_dim=n_classes)

    eval_plugin = EvaluationPlugin(
            accuracy_metrics(minibatch=True, epoch=False, experience=True, stream=True),
            loss_metrics(minibatch=True, epoch=False, experience=True, stream=True),
        #    timing_metrics(epoch=True, epoch_running=True),
        #    forgetting_metrics(experience=True, stream=True),
        #    cpu_usage_metrics(experience=True),
        #    confusion_matrix_metrics(num_classes=scenario.n_classes, save_image=False,
        #                             stream=True),
        #    disk_usage_metrics(minibatch=True, epoch=True, experience=True, stream=True),
            loggers=[interactive_logger])

    for counter in range(num_runs):
        print("*"*20)
        print(f" Starting Repeatation Number {counter} out of {num_runs}")
        print("*"*20)

        buffer_images = []
        buffer_labels = []

        LwfModel = LwF(model=modellwf,optimizer=SGD(modellwf.parameters(), lr=learning_rate, momentum=0.9),train_mb_size=train_batch_size
        ,eval_mb_size=eval_batch_size, criterion=CrossEntropyLoss(),temperature=temperature,alpha=alpha,train_epochs=epochs,device=device) # EWC replay model

        ewcModel = EWC(model=modelewc,optimizer=SGD(modelewc.parameters(), lr=learning_rate, momentum=0.9),train_mb_size=train_batch_size,
        eval_mb_size=eval_batch_size, ewc_lambda=ewc_lambda, criterion=CrossEntropyLoss(), train_epochs=epochs,device=device)
        #lambda=0.001

        siModel = SynapticIntelligence(model=modelsi,optimizer=SGD(modelewc.parameters(), lr=learning_rate, momentum=0.9),
        train_mb_size=train_batch_size, eval_mb_size=eval_batch_size, si_lambda=ewc_lambda_si,criterion=CrossEntropyLoss(),
        train_epochs=epochs,device=device) 

        naiveModel = Naive(model=modelNaive,optimizer=SGD(modelNaive.parameters(), lr=learning_rate, momentum=0.9),train_mb_size=train_batch_size,
        eval_mb_size=eval_batch_size,criterion=CrossEntropyLoss(),train_epochs=epochs,device=device)

        jointModel = JointTraining(model=modelJoint, epochs=joint_epochs,learning_rate=learning_ratejoint, batch_size=joint_batchSize,num_class=n_classes,
                                   patience=patienceJoint,device=device)

        ## Generator model
        gen_model = VAE(input_dim=input_featureDim, latent_embedding=latent_embedding, device=device).to(device=device)
        gen_class = Vae_Cls_Generator(num_epochs=num_epochsGR, model=gen_model, device=device, learning_rate=learning_rateGR, 
                                      batch_size=batch_sizeGR, patience=patienceGR, )
        
        # Joint Training
        print(" Training the Joint Model ")
        jointModel.train(trainData)
        print("Training completetd")

        ## Training and Evaluation
        print('Starting experiment...')
        for experience in train_stream:
            print("Start of experience: ", experience.current_experience)
            print("Current Classes: ", experience.classes_in_this_experience)
            print("Training Generator on current experience")
            gen_class.train(experience)
            for digit in experience.classes_in_this_experience:
                temp_img, temp_labels = utility_funcs.buffer_dataGeneration(digit=digit, experience=experience, num_examples=num_syntheticExamplesPerDigit,
                                            device=device,model=gen_model,numbOf_orgExamples=num_originalExamplesPerDigit,batch_size=batch_sizeGR)
                buffer_images.append(temp_img)
                buffer_labels.append(temp_labels)

            # Naive model training
            print("Training the Naive Model")
            naiveModel.train(experience)
            print('Training completed')

            ## Benchmark and buffer data generation 
            print("generating benchmark dataset")
            exp_data = utility_funcs.benchmarkDataPrep(experience=experience,device=device,buffer_data=buffer_images,
            buffer_label=buffer_labels)
        
            ## for temp_data in DataLoader(exp_data,batch_size=len(exp_data)):
            scenario_exp = nc_benchmark(exp_data,exp_data,n_experiences=1,task_labels=False)
            data_expTrain = scenario_exp.train_stream
            print("----------------------------------Done----------------------------------")
            for new_exp in data_expTrain:
                print("CLasses in the modified experience ",new_exp.classes_in_this_experience)
                print("Training EWC Model")
                ewcModel.train(new_exp)  #Avalanche Benchmark strategy
                print('Training completed')

                print("Training LWF Model")
                LwfModel.train(new_exp)
                print('Training completed')

                print("Training SI Model")
                siModel.train(new_exp)
                print('Training completed')

            ## Evaluation
            print("computing accuracy for EWC Model")
            bench_resultsEWC = ewcModel.eval(test_stream)
            print("*"*20)

            print("computing accuracy for LWF Model")
            bench_resultsLWF = LwfModel.eval(test_stream)
            print("*"*20)

            print("computing accuracy for SI Model")
            bench_resultsSI = siModel.eval(test_stream)
            print("*"*20)

            print("computing accuracy for Naive Model")
            bench_resultsNaive = naiveModel.eval(test_stream)
            print("*"*20)

            print("computing accuracy for Joint Model")
            bench_resultsJoint = jointModel.eval(test_stream)
            print("*"*20)

        #Saving the result for plots
        benchResultArrayEWC.append(utility_funcs.dataPrepToPlot(bench_resultsEWC,len(train_stream)))
        benchResultArrayLWF.append(utility_funcs.dataPrepToPlot(bench_resultsLWF,len(train_stream)))
        benchResultArraySI.append(utility_funcs.dataPrepToPlot(bench_resultsSI,len(train_stream)))
        benchResultArrayNaive.append(utility_funcs.dataPrepToPlot(bench_resultsNaive,len(train_stream)))
        # benchResultArrayJoint.append(dataPrepToPlot(bench_resultsJoint,len(train_stream)))
        benchResultArrayJoint.append(bench_resultsJoint)

    meanBenchEWC = np.round(np.sum(benchResultArrayEWC,axis=0)/num_runs, decimals=2)
    meanBenchLWF = np.round(np.sum(benchResultArrayLWF,axis=0)/num_runs, decimals=2)
    meanBenchSI = np.round(np.sum(benchResultArraySI,axis=0)/num_runs, decimals=2)
    meanBenchNaive = np.round(np.sum(benchResultArrayNaive,axis=0)/num_runs, decimals=2)
    meanBenchJoint = np.round(np.sum(benchResultArrayJoint,axis=0)/num_runs, decimals=2)

    stdBenchEWC = np.round(np.std(benchResultArrayEWC,axis=0), decimals=8)    #Mean after n runs runs
    stdBenchLWF = np.round(np.std(benchResultArrayLWF,axis=0), decimals=8)
    stdBenchSI = np.round(np.std(benchResultArraySI,axis=0), decimals=8)
    stdBenchNaive = np.round(np.std(benchResultArrayNaive,axis=0), decimals=8)
    stdBenchJoint = np.round(np.std(benchResultArrayJoint,axis=0), decimals=8)

    utility_funcs.barPlotMeanPred(meanBenchEWC = meanBenchEWC,meanBenchLWF = meanBenchLWF, meanBenchSI = meanBenchSI, meanBenchNaive = meanBenchNaive, meanBenchJoint=meanBenchJoint, 
                    stdBenchEWC = stdBenchEWC, stdBenchLWF = stdBenchLWF, stdBenchSI = stdBenchSI, stdBenchNaive = stdBenchNaive, stdBenchJoint = stdBenchJoint, 
                    n_experinces=n_experiences)

    print(f"The mean value after 5 experinces for {num_runs} for EWC model is {np.sum(meanBenchEWC)/n_experiences}")
    print(f"The Corresponding std. after 5 experinces for {num_runs} for EWC model model is {np.sum(stdBenchEWC)/n_experiences}")

    print(f"The mean value after 5 experinces for {num_runs} for LWF model is {np.sum(meanBenchLWF)/n_experiences}")
    print(f"The Corresponding std. after 5 experinces for {num_runs} for LWF model is {np.sum(stdBenchLWF)/n_experiences}")
    
    print(f"The mean value after 5 experinces for {num_runs} for SI model is {np.sum(meanBenchSI)/n_experiences}")
    print(f"The Corresponding std. after 5 experinces for {num_runs} for SI model is {np.sum(stdBenchSI)/n_experiences}")

    print(f"The mean value after 5 experinces for {num_runs} for Naive model is {np.sum(meanBenchNaive)/n_experiences}")
    print(f"The Corresponding std. after 5 experinces for {num_runs} for Naive model is {np.sum(stdBenchNaive)/n_experiences}")

    print(f"The mean value after 5 experinces for {num_runs} for Joint model is {np.sum(meanBenchJoint)/n_experiences}")
    print(f"The Corresponding std. after 5 experinces for {num_runs} for Joint model is {np.sum(stdBenchJoint)/n_experiences}")


if __name__=="__main__":
    main()
