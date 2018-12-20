import tensorflow as tf

# lookup and concat source inputs
def multi_input_encoder_emb_lookup_fn(embedding_encoder, source):
  with tf.Session() as sess:
    sess.run(tf.tables_initializer())
    sess.run(tf.global_variables_initializer())
    # sess.run(batched_iter.initializer,feed_dict={skip_count: 3})
    print("BATCH:", sess.run(source))
    # print("id",  sess.run(tgt_eos_id),  sess.run(tgt_sos_id))