#!/usr/bin/env bash

data_dir=/iesl/canvas/strubell/data/nmt_viet_multi

python -m nmt.nmt \
    --attention=scaled_luong \
    --src=vi --tgt=en \
    --vocab_prefix=$data_dir/vocab_combined  \
    --train_prefix=$data_dir/train \
    --dev_prefix=$data_dir/tst2012  \
    --test_prefix=$data_dir/tst2013 \
    --out_dir=nmt_model_multi \
    --num_train_steps=12000 \
    --steps_per_stats=100 \
    --num_layers=2 \
    --num_units=128 \
    --dropout=0.2 \
    --metrics=bleu
