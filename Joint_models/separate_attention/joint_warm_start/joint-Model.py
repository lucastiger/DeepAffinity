## importing part
from __future__ import division, print_function, absolute_import
import statsmodels.api as sm
import gzip
import os
import re
import tarfile
import math
import random
import sys
import time
import logging
import numpy as np
import math

from tensorflow.python.platform import gfile
import tensorflow as tf
import tflearn
from tflearn.layers.core import input_data, dropout, fully_connected
from tflearn.layers.conv import conv_2d, max_pool_2d,conv_1d,max_pool_1d
from tflearn.layers.normalization import local_response_normalization
from tflearn.layers.estimator import regression
from tflearn.layers.merge_ops import merge
from tflearn.layers.recurrent import bidirectional_rnn, BasicLSTMCell,GRUCell
#from recurrent import bidirectional_rnn, BasicLSTMCell,GRUCell

random.seed(1234)
#### data and vocabulary

data_dir="./data"
vocab_size_compound=68
vocab_size_protein=76
comp_MAX_size=100
protein_MAX_size=152
vocab_compound="vocab_compound"
vocab_protein="vocab_protein"
batch_size = 64

GRU_size_prot=256
GRU_size_drug=128

dev_perc=0.1

## Padding part
_PAD = b"_PAD"
_GO = b"_GO"
_EOS = b"_EOS"
_UNK = b"_UNK"
_START_VOCAB = [_PAD, _GO, _EOS, _UNK]
PAD_ID = 0
GO_ID = 1
EOS_ID = 2
UNK_ID = 3
_WORD_SPLIT = re.compile(b"(\S)")
_WORD_SPLIT_2 = re.compile(b",")
_DIGIT_RE = re.compile(br"\d")


## functions
def basic_tokenizer(sentence,condition):
  """Very basic tokenizer: split the sentence into a list of tokens."""
  words = []
  for space_separated_fragment in sentence.strip().split():
    if condition ==0:
        l = _WORD_SPLIT.split(space_separated_fragment)
        del l[0::2]
    elif condition == 1:
        l = _WORD_SPLIT_2.split(space_separated_fragment)
    words.extend(l)
  return [w for w in words if w]

def sentence_to_token_ids(sentence, vocabulary,condition,normalize_digits=False):

  words = basic_tokenizer(sentence,condition)
  if not normalize_digits:
    return [vocabulary.get(w, UNK_ID) for w in words]
  return [vocabulary.get(_DIGIT_RE.sub(b"0", w), UNK_ID) for w in words]


def initialize_vocabulary(vocabulary_path):
  if gfile.Exists(vocabulary_path):
    rev_vocab = []
    with gfile.GFile(vocabulary_path, mode="rb") as f:
      rev_vocab.extend(f.readlines())
    rev_vocab = [tf.compat.as_bytes(line.strip()) for line in rev_vocab]
    vocab = dict([(x, y) for (y, x) in enumerate(rev_vocab)])
    return vocab, rev_vocab
  else:
    raise ValueError("Vocabulary file %s not found.", vocabulary_path)



def data_to_token_ids(data_path, target_path, vocabulary_path, condition,normalize_digits=False):
  if not gfile.Exists(target_path):
    print("Tokenizing data in %s" % data_path)
    vocab, _ = initialize_vocabulary(vocabulary_path)
    with gfile.GFile(data_path, mode="rb") as data_file:
      with gfile.GFile(target_path, mode="w") as tokens_file:
        counter = 0
        for line in data_file:
          counter += 1
          if counter % 100000 == 0:
            print("  tokenizing line %d" % counter)
          token_ids = sentence_to_token_ids(tf.compat.as_bytes(line), vocab, condition,normalize_digits)
          tokens_file.write(" ".join([str(tok) for tok in token_ids]) + "\n")


def read_data(source_path,MAX_size):
  data_set = []
  mycount=0
  with tf.gfile.GFile(source_path, mode="r") as source_file:
      source = source_file.readline()
      counter = 0
      while source:
        counter += 1
        if counter % 100000 == 0:
          print("  reading data line %d" % counter)
          sys.stdout.flush()
        source_ids = [int(x) for x in source.split()]
        if len(source_ids) < MAX_size:
           pad = [PAD_ID] * (MAX_size - len(source_ids))
           data_set.append(list(source_ids + pad))
           mycount=mycount+1
        elif len(source_ids) == MAX_size:
           data_set.append(list(source_ids))
           mycount=mycount+1
        else:
           print("there is a data with length bigger than the max\n")
           print(len(source_ids))
        source = source_file.readline()
  return data_set

def prepare_data(data_dir, train_path, vocabulary_size,vocab,max_size,condition):
  vocab_path = os.path.join(data_dir, vocab)

  train_ids_path = train_path + (".ids%d" % vocabulary_size)
  data_to_token_ids(train_path, train_ids_path, vocab_path,condition)
  train_set = read_data(train_ids_path,max_size)
  
  return train_set

def normalize_labels(label):
   x = []
   micro=1000000
   for i in label:
      if i ==0:
         print(i)
      m = -math.log10(i)+math.log10(micro)
      x.append(m)
   return x


def read_labels(path):
    x = []
    f = open(path, "r") 
    for line in f:
         if (line[0]=="<")or(line[0]==">"): 
            print("Inequality in IC50!!!\n")
         else:
            x.append(float(line)) 
 
    #y = normalize_labels(x)
    return x


def read_initial_state_weigths(path,size1,size2):
    x = []
    f = open(path, "r")
    count = 0;
    for line in f:
       y = [float(n) for n in line.split(" ")]
       if len(y) == size2:
          x.append(y)
          count = count+1
       else:
          print("not exactly equal to size2!!!!!!")
    
    return x

def  train_dev_split(train_protein,train_compound,train_IC50,dev_perc,comp_MAX_size,protein_MAX_size,batch_size):
    num_whole= len(train_IC50)
    num_train = math.ceil(num_whole*(1-dev_perc)/batch_size)*batch_size
    num_dev = math.floor((num_whole - num_train)/batch_size)*batch_size

    index_total = range(0,num_whole)
    index_dev = sorted(random.sample(index_total,num_dev))
    remain = list(set(index_total)^set(index_dev))
    index_train = sorted(random.sample(remain,num_train))

    compound_train = [train_compound[i] for i in index_train]
    compound_train = np.reshape(compound_train,[len(compound_train),comp_MAX_size])
    compound_dev = [train_compound[i] for i in index_dev]
    compound_dev = np.reshape(compound_dev,[len(compound_dev),comp_MAX_size])

    IC50_train = [train_IC50[i] for i in index_train]
    IC50_train = np.reshape(IC50_train,[len(IC50_train),1])
    IC50_dev = [train_IC50[i] for i in index_dev]
    IC50_dev = np.reshape(IC50_dev,[len(IC50_dev),1])

    protein_train = [train_protein[i] for i in index_train]
    protein_train = np.reshape(protein_train,[len(protein_train),protein_MAX_size])
    protein_dev = [train_protein[i] for i in index_dev]
    protein_dev = np.reshape(protein_dev,[len(protein_dev),protein_MAX_size])

    return compound_train, compound_dev, IC50_train, IC50_dev, protein_train, protein_dev

################ Reading initial states and weigths 
prot_gru_1_candidate_bias_init = read_initial_state_weigths("./data/prot_init/cell_0_candidate_bias.txt",1,GRU_size_prot)
prot_gru_1_candidate_bias_init = tf.convert_to_tensor(np.reshape(prot_gru_1_candidate_bias_init,[GRU_size_prot]),dtype=tf.float32)

prot_gru_1_candidate_kernel_init = read_initial_state_weigths("./data/prot_init/cell_0_candidate_kernel.txt",2*GRU_size_prot,GRU_size_prot)
prot_gru_1_candidate_kernel_init = tf.convert_to_tensor(np.reshape(prot_gru_1_candidate_kernel_init,[2*GRU_size_prot,GRU_size_prot]),dtype=tf.float32)

prot_gru_1_gates_bias_init = read_initial_state_weigths("./data/prot_init/cell_0_gates_bias.txt",1,2*GRU_size_prot)
prot_gru_1_gates_bias_init = tf.convert_to_tensor(np.reshape(prot_gru_1_gates_bias_init,[2*GRU_size_prot]),dtype=tf.float32)

prot_gru_1_gates_kernel_init = read_initial_state_weigths("./data/prot_init/cell_0_gates_kernel.txt",2*GRU_size_prot,2*GRU_size_prot)
prot_gru_1_gates_kernel_init = tf.convert_to_tensor(np.reshape(prot_gru_1_gates_kernel_init,[2*GRU_size_prot,2*GRU_size_prot]),dtype=tf.float32)

prot_gru_2_candidate_bias_init = read_initial_state_weigths("./data/prot_init/cell_1_candidate_bias.txt",1,GRU_size_prot)
prot_gru_2_candidate_bias_init = tf.convert_to_tensor(np.reshape(prot_gru_2_candidate_bias_init,[GRU_size_prot]),dtype=tf.float32)

prot_gru_2_candidate_kernel_init = read_initial_state_weigths("./data/prot_init/cell_1_candidate_kernel.txt",2*GRU_size_prot,GRU_size_prot)
prot_gru_2_candidate_kernel_init = tf.convert_to_tensor(np.reshape(prot_gru_2_candidate_kernel_init,[2*GRU_size_prot,GRU_size_prot]),dtype=tf.float32)

prot_gru_2_gates_bias_init = read_initial_state_weigths("./data/prot_init/cell_1_gates_bias.txt",1,2*GRU_size_prot)
prot_gru_2_gates_bias_init = tf.convert_to_tensor(np.reshape(prot_gru_2_gates_bias_init,[2*GRU_size_prot]),dtype=tf.float32)

prot_gru_2_gates_kernel_init = read_initial_state_weigths("./data/prot_init/cell_1_gates_kernel.txt",2*GRU_size_prot,2*GRU_size_prot)
prot_gru_2_gates_kernel_init = tf.convert_to_tensor(np.reshape(prot_gru_2_gates_kernel_init,[2*GRU_size_prot,2*GRU_size_prot]),dtype=tf.float32)

prot_embd_init = read_initial_state_weigths("./data/prot_init/embedding_W.txt",vocab_size_protein,GRU_size_prot)
prot_embd_init = tf.convert_to_tensor(np.reshape(prot_embd_init,[vocab_size_protein,GRU_size_prot]),dtype=tf.float32)

prot_init_state_1 = read_initial_state_weigths("./data/prot_init/first_layer_states.txt",batch_size,GRU_size_prot)
prot_init_state_1 = tf.convert_to_tensor(np.reshape(prot_init_state_1,[batch_size,GRU_size_prot]),dtype=tf.float32)

prot_init_state_2 = read_initial_state_weigths("./data/prot_init/second_layer_states.txt",batch_size,GRU_size_prot)
prot_init_state_2 = tf.convert_to_tensor(np.reshape(prot_init_state_2,[batch_size,GRU_size_prot]),dtype=tf.float32)


drug_gru_1_candidate_bias_init = read_initial_state_weigths("./data/drug_init/cell_0_candidate_bias.txt",1,GRU_size_drug)
drug_gru_1_candidate_bias_init = tf.convert_to_tensor(np.reshape(drug_gru_1_candidate_bias_init,[GRU_size_drug]),dtype=tf.float32)

drug_gru_1_candidate_kernel_init = read_initial_state_weigths("./data/drug_init/cell_0_candidate_kernel.txt",2*GRU_size_drug,GRU_size_drug)
drug_gru_1_candidate_kernel_init = tf.convert_to_tensor(np.reshape(drug_gru_1_candidate_kernel_init,[2*GRU_size_drug,GRU_size_drug]),dtype=tf.float32)

drug_gru_1_gates_bias_init = read_initial_state_weigths("./data/drug_init/cell_0_gates_bias.txt",1,2*GRU_size_drug)
drug_gru_1_gates_bias_init = tf.convert_to_tensor(np.reshape(drug_gru_1_gates_bias_init,[2*GRU_size_drug]),dtype=tf.float32)

drug_gru_1_gates_kernel_init = read_initial_state_weigths("./data/drug_init/cell_0_gates_kernel.txt",2*GRU_size_drug,2*GRU_size_drug)
drug_gru_1_gates_kernel_init = tf.convert_to_tensor(np.reshape(drug_gru_1_gates_kernel_init,[2*GRU_size_drug,2*GRU_size_drug]),dtype=tf.float32)

drug_gru_2_candidate_bias_init = read_initial_state_weigths("./data/drug_init/cell_1_candidate_bias.txt",1,GRU_size_drug)
drug_gru_2_candidate_bias_init = tf.convert_to_tensor(np.reshape(drug_gru_2_candidate_bias_init,[GRU_size_drug]),dtype=tf.float32)

drug_gru_2_candidate_kernel_init = read_initial_state_weigths("./data/drug_init/cell_1_candidate_kernel.txt",2*GRU_size_drug,GRU_size_drug)
drug_gru_2_candidate_kernel_init = tf.convert_to_tensor(np.reshape(drug_gru_2_candidate_kernel_init,[2*GRU_size_drug,GRU_size_drug]),dtype=tf.float32)

drug_gru_2_gates_bias_init = read_initial_state_weigths("./data/drug_init/cell_1_gates_bias.txt",1,2*GRU_size_drug)
drug_gru_2_gates_bias_init = tf.convert_to_tensor(np.reshape(drug_gru_2_gates_bias_init,[2*GRU_size_drug]),dtype=tf.float32)

drug_gru_2_gates_kernel_init = read_initial_state_weigths("./data/drug_init/cell_1_gates_kernel.txt",2*GRU_size_drug,2*GRU_size_drug)
drug_gru_2_gates_kernel_init = tf.convert_to_tensor(np.reshape(drug_gru_2_gates_kernel_init,[2*GRU_size_drug,2*GRU_size_drug]),dtype=tf.float32)

drug_embd_init = read_initial_state_weigths("./data/drug_init/embedding_W.txt",vocab_size_compound,GRU_size_drug)
drug_embd_init = tf.convert_to_tensor(np.reshape(drug_embd_init,[vocab_size_compound,GRU_size_drug]),dtype=tf.float32)

drug_init_state_1 = read_initial_state_weigths("./data/drug_init/first_layer_states.txt",batch_size,GRU_size_drug)
drug_init_state_1 = tf.convert_to_tensor(np.reshape(drug_init_state_1,[batch_size,GRU_size_drug]),dtype=tf.float32)

drug_init_state_2 = read_initial_state_weigths("./data/drug_init/second_layer_states.txt",batch_size,GRU_size_drug)
drug_init_state_2 = tf.convert_to_tensor(np.reshape(drug_init_state_2,[batch_size,GRU_size_drug]),dtype=tf.float32)

## preparing data 

ER_protein = prepare_data(data_dir,"./data/ER_sps",vocab_size_protein,vocab_protein,protein_MAX_size,1)
ER_compound = prepare_data(data_dir,"./data/ER_smile",vocab_size_compound,vocab_compound,comp_MAX_size,0)
ER_IC50 = read_labels("./data/ER_ic50")

GPCR_protein = prepare_data(data_dir,"./data/GPCR_sps",vocab_size_protein,vocab_protein,protein_MAX_size,1)
GPCR_compound = prepare_data(data_dir,"./data/GPCR_smile",vocab_size_compound,vocab_compound,comp_MAX_size,0)
GPCR_IC50 = read_labels("./data/GPCR_ic50")

kinase_protein = prepare_data(data_dir,"./data/kinase_sps",vocab_size_protein,vocab_protein,protein_MAX_size,1)
kinase_compound = prepare_data(data_dir,"./data/kinase_smile",vocab_size_compound,vocab_compound,comp_MAX_size,0)
kinase_IC50 = read_labels("./data/kinase_ic50")

channel_protein = prepare_data(data_dir,"./data/channel_sps",vocab_size_protein,vocab_protein,protein_MAX_size,1)
channel_compound = prepare_data(data_dir,"./data/channel_smile",vocab_size_compound,vocab_compound,comp_MAX_size,0)
channel_IC50 = read_labels("./data/channel_ic50")


train_protein = prepare_data(data_dir,"./data/train_sps",vocab_size_protein,vocab_protein,protein_MAX_size,1)
train_compound = prepare_data(data_dir,"./data/train_smile",vocab_size_compound,vocab_compound,comp_MAX_size,0)
train_IC50 = read_labels("./data/train_ic50")

test_protein = prepare_data(data_dir,"./data/test_sps",vocab_size_protein,vocab_protein,protein_MAX_size,1)
test_compound = prepare_data(data_dir,"./data/test_smile",vocab_size_compound,vocab_compound,comp_MAX_size,0)
test_IC50 = read_labels("./data/test_ic50")

#train_protein += test_protein + ER_protein + GPCR_protein + kinase_protein + channel_protein
#train_compound += test_compound + ER_compound + GPCR_compound + kinase_compound + channel_compound
train_IC50 += test_IC50 + ER_IC50 + GPCR_IC50 + kinase_IC50 + channel_IC50

## separating train,dev, test data
compound_train, compound_dev, IC50_train, IC50_dev, protein_train, protein_dev = train_dev_split(train_protein,train_compound,train_IC50,dev_perc,comp_MAX_size,protein_MAX_size,batch_size)

## RNN for protein
prot_data = input_data(shape=[None, protein_MAX_size])
prot_embd = tflearn.embedding(prot_data, input_dim=vocab_size_protein, output_dim=GRU_size_prot)
prot_gru_1 = tflearn.gru(prot_embd, GRU_size_prot,initial_state= prot_init_state_1,trainable=True,return_seq=True,restore=False)
prot_gru_1 = tf.stack(prot_gru_1,axis=1)
prot_gru_2 = tflearn.gru(prot_gru_1, GRU_size_prot,initial_state= prot_init_state_2,trainable=True,return_seq=True,restore=False)
prot_gru_2=tf.stack(prot_gru_2,axis=1)
W_prot = tflearn.variables.variable(name="Attn_W_prot",shape=[GRU_size_prot,GRU_size_prot],initializer=tf.random_normal([GRU_size_prot,GRU_size_prot],stddev=0.1),restore=False)
b_prot = tflearn.variables.variable(name="Attn_b_prot",shape=[GRU_size_prot],initializer=tf.random_normal([GRU_size_prot],stddev=0.1),restore=False)
U_prot = tflearn.variables.variable(name="Attn_U_prot",shape=[GRU_size_prot],initializer=tf.random_normal([GRU_size_prot],stddev=0.1),restore=False)
V_prot = tf.tanh(tf.tensordot(prot_gru_2,W_prot,axes=1)+b_prot)
VU_prot = tf.tensordot(V_prot,U_prot,axes=1)
alphas_prot = tf.nn.softmax(VU_prot,name='alphas')
Attn_prot = tf.reduce_sum(prot_gru_2 *tf.expand_dims(alphas_prot,-1),1)
Attn_prot_reshape = tflearn.reshape(Attn_prot, [-1, GRU_size_prot,1])
conv_1 = conv_1d(Attn_prot_reshape, 64, 8,4, activation='leakyrelu', weights_init="xavier",regularizer="L2",name='conv1')

pool_1 = max_pool_1d(conv_1, 4,name='pool1')
prot_reshape_6 = tflearn.reshape(pool_1, [-1, 64*16])



prot_embd_W = []
prot_gru_1_gate_matrix = []
prot_gru_1_gate_bias = []
prot_gru_1_candidate_matrix = []
prot_gru_1_candidate_bias = []
prot_gru_2_gate_matrix = []
prot_gru_2_gate_bias = []
prot_gru_2_candidate_matrix = []
prot_gru_2_candidate_bias = []
for v in tf.global_variables():
   if "GRU/GRU/GRUCell/Gates/Linear/Matrix" in v.name :
      prot_gru_1_gate_matrix.append(v)
   elif "GRU/GRU/GRUCell/Candidate/Linear/Matrix" in v.name :
      prot_gru_1_candidate_matrix.append(v)
   elif "GRU/GRU/GRUCell/Gates/Linear/Bias" in v.name :
      prot_gru_1_gate_bias.append(v)
   elif "GRU/GRU/GRUCell/Candidate/Linear/Bias" in v.name :
      prot_gru_1_candidate_bias.append(v)
   elif "GRU_1/GRU_1/GRUCell/Gates/Linear/Matrix" in v.name :
      prot_gru_2_gate_matrix.append(v)
   elif "GRU_1/GRU_1/GRUCell/Candidate/Linear/Matrix" in v.name :
      prot_gru_2_candidate_matrix.append(v)
   elif "GRU_1/GRU_1/GRUCell/Gates/Linear/Bias" in v.name :
      prot_gru_2_gate_bias.append(v)
   elif "GRU_1/GRU_1/GRUCell/Candidate/Linear/Bias" in v.name :
      prot_gru_2_candidate_bias.append(v)
   elif "Embedding" in v.name:
      prot_embd_W.append(v)


## RNN for drug
drug_data = input_data(shape=[None, comp_MAX_size])
drug_embd = tflearn.embedding(drug_data, input_dim=vocab_size_compound, output_dim=GRU_size_drug)
drug_gru_1 = tflearn.gru(drug_embd,GRU_size_drug,initial_state= drug_init_state_1,trainable=True,return_seq=True,restore=False)
drug_gru_1 = tf.stack(drug_gru_1,1)
drug_gru_2 = tflearn.gru(drug_gru_1, GRU_size_drug,initial_state= drug_init_state_2,trainable=True,return_seq=True,restore=False)
drug_gru_2=tf.stack(drug_gru_2,axis=1)
W_drug = tflearn.variables.variable(name="Attn_W_drug",shape=[GRU_size_drug,GRU_size_drug],initializer=tf.random_normal([GRU_size_drug,GRU_size_drug],stddev=0.1),restore=False)
b_drug = tflearn.variables.variable(name="Attn_b_drug",shape=[GRU_size_drug],initializer=tf.random_normal([GRU_size_drug],stddev=0.1),restore=False)
U_drug = tflearn.variables.variable(name="Attn_U_drug",shape=[GRU_size_drug],initializer=tf.random_normal([GRU_size_drug],stddev=0.1),restore=False)
V_drug = tf.tanh(tf.tensordot(drug_gru_2,W_drug,axes=1)+b_drug)
VU_drug = tf.tensordot(V_drug,U_drug,axes=1)
alphas_drug = tf.nn.softmax(VU_drug,name='alphas')
Attn_drug = tf.reduce_sum(drug_gru_2 *tf.expand_dims(alphas_drug,-1),1)
Attn_drug_reshape = tflearn.reshape(Attn_drug, [-1, GRU_size_drug,1])
conv_3 = conv_1d(Attn_drug_reshape, 64, 4,2, activation='leakyrelu', weights_init="xavier",regularizer="L2",name='conv3')
pool_3 = max_pool_1d(conv_3, 4,name='pool3')
drug_reshape_6 = tflearn.reshape(pool_3, [-1, 64*16])

drug_embd_W = []
drug_gru_1_gate_matrix = []
drug_gru_1_gate_bias = []
drug_gru_1_candidate_matrix = []
drug_gru_1_candidate_bias = []
drug_gru_2_gate_matrix = []
drug_gru_2_gate_bias = []
drug_gru_2_candidate_matrix = []
drug_gru_2_candidate_bias = []
for v in tf.global_variables():
   print(v)
   if "GRU_2/GRU_2/GRUCell/Gates/Linear/Matrix" in v.name :
      drug_gru_1_gate_matrix.append(v)
   elif "GRU_2/GRU_2/GRUCell/Candidate/Linear/Matrix" in v.name :
      drug_gru_1_candidate_matrix.append(v)
   elif "GRU_2/GRU_2/GRUCell/Gates/Linear/Bias" in v.name :
      drug_gru_1_gate_bias.append(v)
   elif "GRU_2/GRU_2/GRUCell/Candidate/Linear/Bias" in v.name :
      drug_gru_1_candidate_bias.append(v)
   elif "GRU_3/GRU_3/GRUCell/Gates/Linear/Matrix" in v.name :
      drug_gru_2_gate_matrix.append(v)
   elif "GRU_3/GRU_3/GRUCell/Candidate/Linear/Matrix" in v.name :
      drug_gru_2_candidate_matrix.append(v)
   elif "GRU_3/GRU_3/GRUCell/Gates/Linear/Bias" in v.name :
      drug_gru_2_gate_bias.append(v)
   elif "GRU_3/GRU_3/GRUCell/Candidate/Linear/Bias" in v.name :
      drug_gru_2_candidate_bias.append(v)
   elif "Embedding_1" in v.name:
      drug_embd_W.append(v)

merging =  merge([prot_reshape_6,drug_reshape_6],mode='concat',axis=1)
fc_1 = fully_connected(merging, 600, activation='leakyrelu',weights_init="xavier",name='fully1')
drop_2 = dropout(fc_1, 0.8)
fc_2 = fully_connected(drop_2, 300, activation='leakyrelu',weights_init="xavier",name='fully2')
drop_3 = dropout(fc_2, 0.8)
linear = fully_connected(drop_3, 1, activation='linear',name='fully3')
reg = regression(linear, optimizer='adam', learning_rate=0.0001,
                     loss='mean_square', name='target')

# Training
model = tflearn.DNN(reg, tensorboard_verbose=0,tensorboard_dir='./mytensor/',checkpoint_path="./checkpoints/")

#model.load('checkpoints-370700')

######### Setting weights

model.set_weights(prot_gru_1_gate_matrix[0],prot_gru_1_gates_kernel_init)
model.set_weights(prot_gru_1_gate_bias[0],prot_gru_1_gates_bias_init)
model.set_weights(prot_gru_1_candidate_matrix[0],prot_gru_1_candidate_kernel_init)
model.set_weights(prot_gru_1_candidate_bias[0],prot_gru_1_candidate_bias_init)
model.set_weights(prot_gru_2_gate_matrix[0],prot_gru_2_gates_kernel_init)
model.set_weights(prot_gru_2_gate_bias[0],prot_gru_2_gates_bias_init)
model.set_weights(prot_gru_2_candidate_matrix[0],prot_gru_2_candidate_kernel_init)
model.set_weights(prot_gru_2_candidate_bias[0],prot_gru_2_candidate_bias_init)


model.set_weights(drug_gru_1_gate_matrix[0],drug_gru_1_gates_kernel_init)
model.set_weights(drug_gru_1_gate_bias[0],drug_gru_1_gates_bias_init)
model.set_weights(drug_gru_1_candidate_matrix[0],drug_gru_1_candidate_kernel_init)
model.set_weights(drug_gru_1_candidate_bias[0],drug_gru_1_candidate_bias_init)
model.set_weights(drug_gru_2_gate_matrix[0],drug_gru_2_gates_kernel_init)
model.set_weights(drug_gru_2_gate_bias[0],drug_gru_2_gates_bias_init)
model.set_weights(drug_gru_2_candidate_matrix[0],drug_gru_2_candidate_kernel_init)
model.set_weights(drug_gru_2_candidate_bias[0],drug_gru_2_candidate_bias_init)


######## training
model.fit([protein_train,compound_train], {'target': IC50_train}, n_epoch=100,batch_size=64,
           validation_set=([protein_dev,compound_dev], {'target': IC50_dev}),
           snapshot_epoch=True, show_metric=True, run_id='joint_model')

# saving save
model.save('my_model')

print("error on dev")
size = 64
length_dev = len(protein_dev)
print(length_dev)
num_bins = math.ceil(length_dev/size)
for i in range(num_bins):
        if i==0:
          y_pred = model.predict([protein_dev[0:size],compound_dev[0:size]])
        elif i < num_bins-1:
          temp = model.predict([protein_dev[(i*size):((i+1)*size)],compound_dev[(i*size):((i+1)*size)]])
          y_pred = np.concatenate((y_pred,temp), axis=0)
        else:
          temp = model.predict([protein_dev[(i*size):length_dev],compound_dev[(i*size):length_dev]])
          y_pred = np.concatenate((y_pred,temp), axis=0)

er=0
for i in range(length_dev):
  er += (y_pred[i]-IC50_dev[i])**2

mse = er/length_dev
print(mse)

results = sm.OLS(y_pred,sm.add_constant(IC50_dev)).fit()
print(results.summary())

print("error on ER")
size = 64
length_ER = len(ER_protein)
print(length_ER)
num_bins = math.ceil(length_ER/size)
for i in range(num_bins):
        if i==0:
          y_pred = model.predict([ER_protein[0:size],ER_compound[0:size]])
        elif i < num_bins-1:
          temp = model.predict([ER_protein[(i*size):((i+1)*size)],ER_compound[(i*size):((i+1)*size)]])
          y_pred = np.concatenate((y_pred,temp), axis=0)
        else:
          temp = model.predict([ER_protein[length_ER-size:length_ER],ER_compound[length_ER-size:length_ER]])
          y_pred = np.concatenate((y_pred,temp[size-length_ER+(i*size):size]), axis=0)

er=0
for i in range(length_ER):
  er += (y_pred[i]-ER_IC50[i])**2

mse = er/length_ER
print(mse)

results = sm.OLS(y_pred,sm.add_constant(ER_IC50)).fit()
print(results.summary())

print("error on GPCR")
size = 64
length_GPCR = len(GPCR_protein)
print(length_GPCR)
num_bins = math.ceil(length_GPCR/size)
for i in range(num_bins):
        if i==0:
          y_pred = model.predict([GPCR_protein[0:size],GPCR_compound[0:size]])
        elif i < num_bins-1:
          temp = model.predict([GPCR_protein[(i*size):((i+1)*size)],GPCR_compound[(i*size):((i+1)*size)]])
          y_pred = np.concatenate((y_pred,temp), axis=0)
        else:
          temp = model.predict([GPCR_protein[length_GPCR-size:length_GPCR],GPCR_compound[length_GPCR-size:length_GPCR]])
          y_pred = np.concatenate((y_pred,temp[size-length_GPCR+(i*size):size]), axis=0)

er=0
for i in range(length_GPCR):
  er += (y_pred[i]-GPCR_IC50[i])**2

mse = er/length_GPCR
print(mse)

results = sm.OLS(y_pred,sm.add_constant(GPCR_IC50)).fit()
print(results.summary())


print("error on kinase")
size = 64
length_kinase = len(kinase_protein)
print(length_kinase)
num_bins = math.ceil(length_kinase/size)
for i in range(num_bins):
        if i==0:
          y_pred = model.predict([kinase_protein[0:size],kinase_compound[0:size]])
        elif i < num_bins-1:
          temp = model.predict([kinase_protein[(i*size):((i+1)*size)],kinase_compound[(i*size):((i+1)*size)]])
          y_pred = np.concatenate((y_pred,temp), axis=0)
        else:
          temp = model.predict([kinase_protein[length_kinase-size:length_kinase],kinase_compound[length_kinase-size:length_kinase]])
          y_pred = np.concatenate((y_pred,temp[size-length_kinase+(i*size):size]), axis=0)

er=0
for i in range(length_kinase):
  er += (y_pred[i]-kinase_IC50[i])**2

mse = er/length_kinase
print(mse)

results = sm.OLS(y_pred,sm.add_constant(kinase_IC50)).fit()
print(results.summary())

print("error on channel")
size = 64
length_channel = len(channel_protein)
print(length_channel)
num_bins = math.ceil(length_channel/size)
for i in range(num_bins):
        if i==0:
          y_pred = model.predict([channel_protein[0:size],channel_compound[0:size]])
        elif i < num_bins-1:
          temp = model.predict([channel_protein[(i*size):((i+1)*size)],channel_compound[(i*size):((i+1)*size)]])
          y_pred = np.concatenate((y_pred,temp), axis=0)
        else:
          temp = model.predict([channel_protein[length_channel-size:length_channel],channel_compound[length_channel-size:length_channel]])
          y_pred = np.concatenate((y_pred,temp[size-length_channel+(i*size):size]), axis=0)

er=0
for i in range(length_channel):
  er += (y_pred[i]-channel_IC50[i])**2

mse = er/length_channel
print(mse)

results = sm.OLS(y_pred,sm.add_constant(channel_IC50)).fit()
print(results.summary())



print("error on train")
size = 64
length_train = len(train_protein)
print(length_train)
num_bins = math.ceil(length_train/size)
for i in range(num_bins):
        if i==0:
          y_pred = model.predict([train_protein[0:size],train_compound[0:size]])
        elif i < num_bins-1:
          temp = model.predict([train_protein[(i*size):((i+1)*size)],train_compound[(i*size):((i+1)*size)]])
          y_pred = np.concatenate((y_pred,temp), axis=0)
        else:
          temp = model.predict([train_protein[length_train-size:length_train],train_compound[length_train-size:length_train]])
          y_pred = np.concatenate((y_pred,temp[size-length_train+(i*size):size]), axis=0)

er=0
for i in range(length_train):
  er += (y_pred[i]-train_IC50[i])**2

mse = er/length_train
print(mse)

results = sm.OLS(y_pred,sm.add_constant(train_IC50)).fit()
print(results.summary())


print("error on test")
size = 64
length_test = len(test_protein)
print(length_test)
num_bins = math.ceil(length_test/size)
for i in range(num_bins):
        if i==0:
          y_pred = model.predict([test_protein[0:size],test_compound[0:size]])
        elif i < num_bins-1:
          temp = model.predict([test_protein[(i*size):((i+1)*size)],test_compound[(i*size):((i+1)*size)]])
          y_pred = np.concatenate((y_pred,temp), axis=0)
        else:
          temp = model.predict([test_protein[length_test-size:length_test],test_compound[length_test-size:length_test]])
          y_pred = np.concatenate((y_pred,temp[size-length_test+(i*size):size]), axis=0)

er=0
for i in range(length_test):
  er += (y_pred[i]-test_IC50[i])**2

mse = er/length_test
print(mse)

results = sm.OLS(y_pred,sm.add_constant(test_IC50)).fit()
print(results.summary())

