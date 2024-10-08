import numpy as np
import torch
import torch.nn.functional as F
import torch.nn as nn
from torch.nn import BCELoss
from torch.utils.data import DataLoader, Subset
from tqdm import tqdm
import time

class Vae_Cls_Generator:
  def __init__(self,num_epochs, model, device,learning_rate,batch_size,patience,reconstruction_term_weight=1):
    self.num_epochs = num_epochs
    self.device = device
    self.model =  model.to(self.device) 
    self.patience = patience
    self.seq_len = 1
    self.loss_fn = F.mse_loss

    self.reconstruction_term_weight = reconstruction_term_weight
    self.learning_rate = learning_rate
    self.batch_size = batch_size

  def train(self,cl_exp,synthetic_imgHeight=None,synthetic_imgWidth=None,buff_images=[]):
    optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)  
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=self.patience, verbose=True)

    train_dataset = cl_exp.dataset
    train_loader = DataLoader(train_dataset, batch_size=self.batch_size,shuffle=False)
    
    for epoch in range(self.num_epochs):
        self.model.train()
        for data in train_loader:
          features = data[0].to(self.device) 
          features = features.reshape(-1, 600, self.seq_len)
          # Forward and back propagation
          encoded, z_mean, z_log_var, decoded = self.model(features)
          # negative sign to make the KL div loss to be positive.
          kl_div = -0.5 * torch.sum(1 + z_log_var 
                                    - z_mean**2 
                                    - torch.exp(z_log_var), 
                                    axis=1) # sum over latent dimension

          batchsize = kl_div.size(0)
          kl_div = kl_div.mean() # average over batch dimension

          pixelwise = self.loss_fn(decoded, features, reduction='none')  # check with reduction ="mean"
          pixelwise = pixelwise.view(batchsize, -1).sum(axis=1) # sum over pixels
          pixelwise = pixelwise.mean() # average over batch dimension
          loss = self.reconstruction_term_weight*pixelwise + kl_div
          
          optimizer.zero_grad()

          loss.backward()
          # Update model parameters
          optimizer.step()
        if epoch%25 ==0:
          print("epoch is ",epoch,"loss is ", loss.item())
        scheduler.step(loss)

  def evaluate(self):
    pass