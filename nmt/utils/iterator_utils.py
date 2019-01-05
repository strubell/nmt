# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""For loading data into NMT models."""
from __future__ import print_function

import collections

import tensorflow as tf

from ..utils import vocab_utils


__all__ = ["BatchedInput", "get_iterator", "get_infer_iterator"]


# NOTE(ebrevdo): When we subclass this, instances' __dict__ becomes empty.
class BatchedInput(
    collections.namedtuple("BatchedInput",
                           ("initializer", "source", "target_input",
                            "target_output", "source_sequence_length",
                            "target_sequence_length"))):
  pass


def lookup_sep_vocabs(vocab_tables, input):
  mapped_tensors = []
  for i, vocab_table in enumerate(vocab_tables):
    mapped_tensor = tf.expand_dims(tf.cast(vocab_table.lookup(input[:, i]), tf.int32), -1)
    mapped_tensors.append(mapped_tensor)
  return tf.concat(mapped_tensors, axis=-1)


def get_infer_iterator(src_dataset,
                       src_vocab_tables,
                       batch_size,
                       eos,
                       src_max_len=None,
                       use_char_encode=False):

  if use_char_encode:
    src_eos_id = vocab_utils.EOS_CHAR_ID
  else:
    # todo assumes all same
    src_eos_id = tf.cast(src_vocab_tables[0].lookup(tf.constant(eos)), tf.int32)
  src_dataset = src_dataset.map(lambda src: tf.string_split([src]).values)

  src_dataset = src_dataset.map(lambda src: tf.string_split(src, delimiter=vocab_utils.INPUT_DELIM))

  # string_split returns a sparse tensor, but we want it to be dense
  src_dataset = src_dataset.map(
    lambda src: tf.sparse_to_dense(src.indices, src.dense_shape, src.values, default_value=''))

  if src_max_len:
    # todo deal with multiple here?
    src_dataset = src_dataset.map(lambda src: src[:src_max_len])

  if use_char_encode:
    # Convert the word strings to character ids
    src_dataset = src_dataset.map(
        lambda src: tf.reshape(vocab_utils.tokens_to_bytes(src), [-1]))
  else:
    # Convert the word strings to ids
    # todo deal with multiple here
    src_dataset = src_dataset.map(
        lambda src: lookup_sep_vocabs(src_vocab_tables, src))

  # Add in the word counts.
  if use_char_encode:
    src_dataset = src_dataset.map(
        lambda src: (src,
                     tf.to_int32(
                         tf.shape(src)[0] / vocab_utils.DEFAULT_CHAR_MAXLEN)))
  else:
    src_dataset = src_dataset.map(lambda src: (src, tf.shape(src)[0]))

  def batching_func(x):
    return x.padded_batch(
        batch_size,
        # The entry is the source line rows;
        # this has unknown-length vectors.  The last entry is
        # the source row size; this is a scalar.
        padded_shapes=(
            tf.TensorShape([None, vocab_utils.NUM_INPUTS_PER_TIMESTEP]),  # src
            tf.TensorShape([])),  # src_len
        # Pad the source sequences with eos tokens.
        # (Though notice we don't generally need to do this since
        # later on we will be masking out calculations past the true sequence.
        padding_values=(
            src_eos_id,  # src
            0))  # src_len -- unused

  batched_dataset = batching_func(src_dataset)
  batched_iter = batched_dataset.make_initializable_iterator()
  (src_ids, src_seq_len) = batched_iter.get_next()
  return BatchedInput(
      initializer=batched_iter.initializer,
      source=src_ids,
      target_input=None,
      target_output=None,
      source_sequence_length=src_seq_len,
      target_sequence_length=None)


def get_iterator(src_dataset,
                 tgt_dataset,
                 src_vocab_tables,
                 tgt_vocab_tables,
                 batch_size,
                 sos,
                 eos,
                 random_seed,
                 num_buckets,
                 src_max_len=None,
                 tgt_max_len=None,
                 num_parallel_calls=4,
                 output_buffer_size=None,
                 skip_count=None,
                 num_shards=1,
                 shard_index=0,
                 reshuffle_each_iteration=True,
                 use_char_encode=False):
  if not output_buffer_size:
    output_buffer_size = batch_size * 1000

  if use_char_encode:
    src_eos_id = vocab_utils.EOS_CHAR_ID
  else:
    src_eos_id = tf.cast(src_vocab_tables[0].lookup(tf.constant(eos)), tf.int32)

  tgt_sos_id = tf.cast(tgt_vocab_tables[0].lookup(tf.constant(sos)), tf.int32)
  tgt_eos_id = tf.cast(tgt_vocab_tables[0].lookup(tf.constant(eos)), tf.int32)

  tgt_sos_ids = tf.cast(tf.stack([tgt_vocab_table.lookup(tf.constant(sos)) for tgt_vocab_table in tgt_vocab_tables]), tf.int32)
  tgt_eos_ids = tf.cast(tf.stack([tgt_vocab_table.lookup(tf.constant(eos)) for tgt_vocab_table in tgt_vocab_tables]), tf.int32)

  src_tgt_dataset = tf.data.Dataset.zip((src_dataset, tgt_dataset))

  src_tgt_dataset = src_tgt_dataset.shard(num_shards, shard_index)
  if skip_count is not None:
    src_tgt_dataset = src_tgt_dataset.skip(skip_count)

  src_tgt_dataset = src_tgt_dataset.shuffle(
      output_buffer_size, random_seed, reshuffle_each_iteration)

  src_tgt_dataset = src_tgt_dataset.map(
      lambda src, tgt: (
          tf.string_split([src]).values, tf.string_split([tgt]).values),
      num_parallel_calls=num_parallel_calls).prefetch(output_buffer_size)

  src_tgt_dataset = src_tgt_dataset.map(
    lambda src, tgt: (
      tf.string_split(src, delimiter=vocab_utils.INPUT_DELIM),
      tf.string_split(tgt, delimiter=vocab_utils.INPUT_DELIM)),
    num_parallel_calls=num_parallel_calls)

  # string_split returns a sparse tensor, but we want it to be dense
  src_tgt_dataset = src_tgt_dataset.map(
    lambda src, tgt: (
      tf.sparse_to_dense(src.indices, src.dense_shape, src.values, default_value=''),
      tf.sparse_to_dense(tgt.indices, tgt.dense_shape, tgt.values, default_value='')),
    num_parallel_calls=num_parallel_calls)

  # Filter zero length input sequences.
  src_tgt_dataset = src_tgt_dataset.filter(
      lambda src, tgt: tf.logical_and(tf.shape(src)[0] > 0, tf.shape(tgt)[0] > 0))

  if src_max_len:
    src_tgt_dataset = src_tgt_dataset.map(
        lambda src, tgt: (src[:src_max_len], tgt),
        num_parallel_calls=num_parallel_calls).prefetch(output_buffer_size)
  if tgt_max_len:
    src_tgt_dataset = src_tgt_dataset.map(
        lambda src, tgt: (src, tgt[:tgt_max_len]),
        num_parallel_calls=num_parallel_calls).prefetch(output_buffer_size)

  # Convert the word strings to ids.  Word strings that are not in the
  # vocab get the lookup table's default_value integer.
  if use_char_encode:
    # todo this is broken (but it shouldn't matter for us)
    src_tgt_dataset = src_tgt_dataset.map(
        lambda src, tgt: (tf.reshape(vocab_utils.tokens_to_bytes(src), [-1]),
                          tf.cast(tgt_vocab_tables.lookup(tgt), tf.int32)),
        num_parallel_calls=num_parallel_calls)
  else:
    src_tgt_dataset = src_tgt_dataset.map(
        lambda src, tgt: (lookup_sep_vocabs(src_vocab_tables, src),
                          lookup_sep_vocabs(tgt_vocab_tables, tgt)),
        num_parallel_calls=num_parallel_calls)

  src_tgt_dataset = src_tgt_dataset.prefetch(output_buffer_size)
  # Create a tgt_input prefixed with <sos> and a tgt_output suffixed with <eos>.
  src_tgt_dataset = src_tgt_dataset.map(
      lambda src, tgt: (src,
                        tf.concat((tf.expand_dims(tgt_sos_ids, 0), tgt), 0),
                        tf.concat((tgt, tf.expand_dims(tgt_eos_ids, 0)), 0)),
                        num_parallel_calls=num_parallel_calls).prefetch(output_buffer_size)

  # Add in sequence lengths.
  if use_char_encode:
    src_tgt_dataset = src_tgt_dataset.map(
        lambda src, tgt_in, tgt_out: (
            src, tgt_in, tgt_out,
            tf.to_int32(tf.shape(src)[0] / vocab_utils.DEFAULT_CHAR_MAXLEN),
            tf.shape(tgt_in)[0]),
        num_parallel_calls=num_parallel_calls)
  else:
    src_tgt_dataset = src_tgt_dataset.map(
        lambda src, tgt_in, tgt_out: (
            src, tgt_in, tgt_out, tf.shape(src)[0], tf.shape(tgt_in)[0]),
        num_parallel_calls=num_parallel_calls)

  src_tgt_dataset = src_tgt_dataset.prefetch(output_buffer_size)

  # Bucket by source sequence length (buckets for lengths 0-9, 10-19, ...)
  def batching_func(x):
    return x.padded_batch(
        batch_size,
        # The first three entries are the source and target line rows;
        # these have unknown-length vectors.  The last two entries are
        # the source and target row sizes; these are scalars.
        padded_shapes=(
            tf.TensorShape([None, vocab_utils.NUM_INPUTS_PER_TIMESTEP]),  # src
            tf.TensorShape([None, vocab_utils.NUM_OUTPUTS_PER_TIMESTEP]),  # tgt_input
            tf.TensorShape([None, vocab_utils.NUM_OUTPUTS_PER_TIMESTEP]),  # tgt_output
            tf.TensorShape([]),  # src_len
            tf.TensorShape([])),  # tgt_len
        # Pad the source and target sequences with eos tokens.
        # (Though notice we don't generally need to do this since
        # later on we will be masking out calculations past the true sequence.
        padding_values=(
            src_eos_id,  # src
            # this assumes they're the same across outputs
            tgt_eos_id,
            tgt_eos_id,
            0,  # src_len -- unused
            0))  # tgt_len -- unused

  if num_buckets > 1:

    def key_func(unused_1, unused_2, unused_3, src_len, tgt_len):
      # Calculate bucket_width by maximum source sequence length.
      # Pairs with length [0, bucket_width) go to bucket 0, length
      # [bucket_width, 2 * bucket_width) go to bucket 1, etc.  Pairs with length
      # over ((num_bucket-1) * bucket_width) words all go into the last bucket.
      if src_max_len:
        bucket_width = (src_max_len + num_buckets - 1) // num_buckets
      else:
        bucket_width = 10

      # Bucket sentence pairs by the length of their source sentence and target
      # sentence.
      bucket_id = tf.maximum(src_len // bucket_width, tgt_len // bucket_width)
      return tf.to_int64(tf.minimum(num_buckets, bucket_id))

    def reduce_func(unused_key, windowed_data):
      return batching_func(windowed_data)

    batched_dataset = src_tgt_dataset.apply(
        tf.contrib.data.group_by_window(
            key_func=key_func, reduce_func=reduce_func, window_size=batch_size))

  else:
    batched_dataset = batching_func(src_tgt_dataset)
  batched_iter = batched_dataset.make_initializable_iterator()

  # with tf.Session() as sess:
  #   sess.run(tf.tables_initializer())
  #   sess.run(tf.global_variables_initializer())
  #   sess.run(batched_iter.initializer,feed_dict={skip_count: 3})
  #   print("BATCH:", sess.run(batched_iter.get_next()))
  #   # print("id",  sess.run(tgt_eos_id),  sess.run(tgt_sos_id))

  (src_ids, tgt_input_ids, tgt_output_ids, src_seq_len,
   tgt_seq_len) = (batched_iter.get_next())
  return BatchedInput(
      initializer=batched_iter.initializer,
      source=src_ids,
      target_input=tgt_input_ids,
      target_output=tgt_output_ids,
      source_sequence_length=src_seq_len,
      target_sequence_length=tgt_seq_len)
