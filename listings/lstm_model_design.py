#!/usr/bin/env python
# coding: utf-8

# In[1]:


import logging
from argparse import ArgumentParser
import numpy as np
from _collections import deque
import matplotlib.pyplot as plt
from h5py import File as H5File
from tensorflow import keras
from tensorflow.keras.callbacks import Callback
from tensorflow.keras.models import Sequential
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input
from tensorflow.keras.layers import Dense
from tensorflow.keras.layers import LSTM
from tensorflow.keras.layers import Dropout
from tensorflow.keras.layers import TimeDistributed
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.regularizers import l2


# # 1. Model variables

# In[15]:


file_name = r'/media/ignazio/DATA/dataset_one_noise.h5'

n_samples_spectrum = 250
n_time_steps = 1

n_batches = 525
batch_size = 128

n_epochs = 150
epochs_array = range(n_epochs)

initial_lr = 1e-2
decay_lr = 1
decay = decay_lr/n_epochs
lrs = [initial_lr*(1/(1+decay*i)) for i in epochs_array]


# In[14]:


# Learning rate plot
plt.style.use("ggplot")
plt.figure()
plt.plot(epochs_array, lrs)
plt.title("Learning Rate Schedule")
plt.xlabel("Epoch #")
plt.ylabel("Learning Rate")
plt.savefig('Learning_rate_schedule_comparison.pdf')


# # 2. Parse and loading data
# ## 2.1 Parse number of fft within file

# In[4]:


class GroupInfo:
    def __init__(self):
        self.path = ''
        self.clean_shape = None
        self.dirty_shape = None
        self.n_fft = 0
        self.attributes = dict()
        
n_fft = 0
groups = []
with H5File(file_name, 'r') as f:
    for main_group_key in f.keys():
        main_group = f[main_group_key]
        for group_key in main_group.keys():
            group = main_group[group_key]

            group_info = GroupInfo()
            group_info.path = group.name
            group_info.clean_shape = group['CLEAN/DB'].shape
            group_info.dirty_shape = group['DIRTY/DB'].shape
            for key in group.attrs.keys():
                group_info.attributes[key] = group.attrs[key]
            if group_info.clean_shape == group_info.dirty_shape:
                print('Found %d FFTs in %s' % (group_info.clean_shape[0], group_info.path))
                group_info.n_fft = group_info.clean_shape[0]
                n_fft += group_info.n_fft
                groups.append(group_info)
            else:
                print('Number of FFTs mismatch\n\tClean %d\n\tDirty %d' %
                            (group_info.clean_shape[0], group_info.dirty_shape[0]))

            if n_batches != 0 and (n_fft/batch_size) >= n_batches:
                break


# ## 2.2 Data loading

# In[5]:


group_idx = 0
target_group = groups[group_idx]

X = np.empty((n_batches*batch_size, n_time_steps, n_samples_spectrum), dtype=np.float64)
Y = np.empty((n_batches*batch_size, n_samples_spectrum), dtype=np.float64)

fft_idx = 0
circular_buffer = deque(maxlen=n_time_steps)
# Generate data
with H5File(file_name, 'r') as f:
    for idx in range(n_batches*batch_size):
        # Store sample
        if not circular_buffer:
            for idx_time in range(n_time_steps - 1):
                circular_buffer.append(f[target_group.path + '/DIRTY/DB'][fft_idx, :, :n_samples_spectrum])
                fft_idx += 1
        circular_buffer.append(f[target_group.path + '/DIRTY/DB'][fft_idx, :, :n_samples_spectrum])
        X[idx, :, :] = circular_buffer
        #X[idx, :, :] = f[target_group.path + '/DIRTY/DB'][fft_idx, :, :self.n_samples_spectrum]
        Y[idx, :] = f[target_group.path + '/CLEAN/DB'][fft_idx, 0, :n_samples_spectrum]
        fft_idx += 1
        if fft_idx >= target_group.n_fft:
            group_idx += 1
            target_group = groups[group_idx]
            fft_idx = 0


# ## 2.3 Data normalization

# In[6]:


Xnorm = np.empty((n_batches*batch_size, n_time_steps, n_samples_spectrum), dtype=np.float64)
Ynorm = np.empty((n_batches*batch_size, n_samples_spectrum), dtype=np.float64)
for idx in range(X[0,0,:].shape[0]):
    Xnorm[:, :, idx] = ((X[:,:,idx] - X[:,:,idx].mean())/(X[:,:,idx] - X[:,:,idx].mean()).std())
    Ynorm[:, idx] = ((Y[:,idx] - Y[:,idx].mean())/(Y[:,idx] - Y[:,idx].mean()).std())
    
stop_idx = int(0.8*n_fft)
x_train = Xnorm[0:stop_idx]
y_train = Ynorm[0:stop_idx]
x_test = Xnorm[stop_idx:]
y_test = Ynorm[stop_idx:]


# # 3. Model
# ## 3.1 Model design

# In[7]:


lstm_units_layer = 512

model = Sequential()
model.add(LSTM(lstm_units_layer, 
               input_shape=(n_time_steps, n_samples_spectrum),
               #return_sequences=False, 
               recurrent_dropout=0.3, 
               activation='relu',
               #stateful=True,
               kernel_initializer='random_normal',
               bias_initializer='zeros'
              ))
#model.add(LSTM(self.n_units,
#                      return_sequences=True, recurrent_dropout=0.3, activation='relu'))
#model.add(LSTM(self.n_units,
#                      return_sequences=False, recurrent_dropout=0.3, activation='relu'))
model.add(Dense(n_samples_spectrum, activation='softmax',kernel_initializer='random_normal',
               bias_initializer='zeros'))
model_info = []
model.summary(print_fn=lambda x: model_info.append(x))
model_info = '\n\t'.join(model_info)
print(model_info)

opt = Adam(lr=initial_lr, decay=decay)
model.compile(#loss='mean_squared_error',
              loss='mse',
              optimizer=opt,
              metrics=['acc', 'mse'])


# ## 3.2 Model train

# In[8]:


history = model.fit(x_train, y_train,
                    epochs=n_epochs, 
                    max_queue_size=50,
                    workers=16,
                    validation_data=(x_test, y_test),
                    shuffle=False)


# In[9]:


history2 = model.fit(x_train, y_train,
                    epochs=n_epochs, 
                    max_queue_size=50,
                    workers=16,
                    validation_data=(x_test, y_test),
                    shuffle=False)


# In[11]:


model.save(r'./checkpoints/LSTM_results.h5')


# In[22]:


acc = np.concatenate((history.history['acc'],history2.history['acc']))
val_acc = np.concatenate((history.history['val_acc'],history2.history['val_acc']))
epochsPlot = range(1,len(acc) + 1)
plt.figure(num=None, figsize=(8,6), dpi=80, facecolor='w', edgecolor='k')
plt.plot(epochsPlot, acc, 'o', label ='Training accuracy')
plt.plot(epochsPlot, val_acc, label ='Validation accuracy')
plt.xlabel('Epochs')
plt.ylabel('Metrics')
plt.title('Training and Validation accuracy')
plt.grid()
plt.legend()

plt.savefig('results_acc_compa.pdf')


# In[23]:


loss = np.concatenate((history.history['loss'],history2.history['loss']))
val_loss = np.concatenate((history.history['val_loss'],history2.history['val_loss']))
epochsPlot = range(1,len(acc) + 1)
plt.figure(num=None, figsize=(8,6), dpi=80, facecolor='w', edgecolor='k')
plt.plot(epochsPlot, loss, 'o', label ='Training loss')
plt.plot(epochsPlot, val_loss, label ='Validation loss')
plt.xlabel('Epochs')
plt.ylabel('Metrics')
plt.title('Training and Validation accuracy')
plt.grid()
plt.legend()

plt.savefig('results_loss_compa.pdf')

