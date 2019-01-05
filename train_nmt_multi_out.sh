#!/usr/bin/env bash

data_dir=/mnt/nfs/work1/shenoy/amee/2018/grouped_traj/code/nmt_viet_multi/
#data_dir=/home/strubell/research/data/nmt_viet_multi

python -m nmt.nmt \
    --attention=scaled_luong \
    --src=vi --tgt=en \
    --vocab_prefix=$data_dir/vocab  \
    --train_prefix=$data_dir/train \
    --dev_prefix=$data_dir/tst2012  \
    --test_prefix=$data_dir/tst2013 \
    --out_dir=nmt_model_multi_out \
    --num_train_steps=10000000 \
    --steps_per_stats=1000 \
    --num_layers=2 \
    --num_units=128 \
    --dropout=0.2 \
    --metrics=bleu
