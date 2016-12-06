from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import numpy as np
import tensorflow as tf
from vae_helpers import *
import time # for calculating how long each epoch takes
import os # for creating folders to write the logs

class VariationalAutoencoder(object):

    def __init__(self,
                latent_dimensions = 10,
                num_epochs = 10,
                learning_rate = 1e-3,
                num_epochs_to_decay_lr = 0,
                num_train = 50000,
                batch_size = 50,
                save_epochs = 50):

        self.LATENTDIM = latent_dimensions
        self.NUM_EPOCS = num_epochs
        self.LEARNING_RATE = learning_rate
        self.NUM_EPOCHS_TO_DECAY_LR = num_epochs_to_decay_lr

        if self.NUM_EPOCHS_TO_DECAY_LR > 0:
            self.DECAY_LR = True
        else:
            self.DECAY_LR = False

        self.NUM_TRAIN = num_train
        self.BATCH_SIZE = min(num_train,batch_size)
        self.SAVE_EPOCS = save_epochs

        self.parameters = []

        with tf.name_scope('image_input'):
            self.x_placeholder  = tf.placeholder("float", shape=[None, 32, 32, 3], name='x-input')  # Batchsize x Number of Pixels

        with tf.name_scope('learning_parameters'):
            self.lr_placeholder  = tf.placeholder("float", None, name='learning_rate')

        self._create_network()
        self._create_loss()
        self._create_optimizer(self.parameters)

        self._make_log_information()
        self._make_summaries()
        self.datasets = None

        self.summary_writer = tf.train.SummaryWriter(self.LOG_DIR, graph=tf.get_default_graph())

    def print_setting(self):
        with open('{}/setting.txt'.format(self.LOG_DIR),'w+') as f:
            # CIFAR SETTINGS
            print('dataset: CIFAR10',file=f)
            print('num train: {}'.format(self.NUM_TRAIN),file=f)
            print('learning rate: {}'.format(self.LEARNING_RATE),file=f)
            print('decay learning rate: {}'.format(self.DECAY_LR),file=f)
            if self.DECAY_LR:
                print('number of epochs to decay learning rate: {}'.format(self.NUM_EPOCHS_TO_DECAY_LR),file=f)
            else:
                print('number of epochs to decay learning rate: 0',file=f)
            print('latent dimensions: {}'.format(self.LATENTDIM),file=f)
            print('batch size: {}'.format(self.BATCH_SIZE),file=f)
            print('num epochs: {}'.format(self.NUM_EPOCS),file=f)

    def _load_datasets(self, num_train = 10):
        # load the CIFAR data -- values lie in 0-1
        mydatasets = read_cifar10_dataset('cifar-10-batches-py/')
        self.datasets = reduce_training_set(mydatasets, num_train)

    def _create_network(self):
        self._encoder_network()
        self.eps_placeholder = tf.placeholder("float", shape=[None, self.LATENTDIM])

        with tf.name_scope('randomize_latent'):
            # The sampled z
            self.z = tf.add(self.z_mean, tf.mul(tf.sqrt(tf.exp(self.z_log_sigma_sq)), self.eps_placeholder))

        self._decoder_network()

    def _create_loss(self):
        with tf.name_scope('loss_layer'):
            # the vectorized input
            x_vectorized  = tf.reshape(self.x_placeholder, [-1,3072], name='x-vectorized')
            x_reconstr_mean_vectorized = tf.reshape(self.x_reconstr_mean, [-1, 3072], name='x_reconstr_mean_vectorized')

            pixel_loss =  tf.reduce_sum( tf.square( x_reconstr_mean_vectorized - x_vectorized ) , 1 )
            self.pixel_loss = pixel_loss / 3072.0

            self.latent_loss = -0.5 * tf.reduce_sum(1 + self.z_log_sigma_sq - tf.square(self.z_mean) - tf.exp(self.z_log_sigma_sq), 1)

            self.latent_loss_mean   = tf.reduce_mean(self.latent_loss)
            self.pixel_loss_mean = tf.reduce_mean(self.pixel_loss)

            self.cost = tf.reduce_mean(self.latent_loss + self.pixel_loss, name='cost_function')   # average over batch

    def _create_optimizer(self,otimization_variables):
        with tf.name_scope('train'):
            self.train_step =  tf.train.AdamOptimizer(learning_rate=self.lr_placeholder).minimize(self.cost, var_list=otimization_variables)

    def _encoder_network(self):
        images = self.x_placeholder

        # conv1_
        with tf.name_scope('enc_conv1_1') as scope:
            kernel = tf.Variable(tf.truncated_normal([3, 3, 3, 32], dtype=tf.float32, stddev= 2.0/np.sqrt(27 + 64) ), name='weights', trainable=True)
            conv = tf.nn.conv2d(images, kernel, [1, 1, 1, 1], padding='SAME')
            biases = tf.Variable(tf.constant(0.1, shape=[32], dtype=tf.float32), trainable=True, name='biases')
            out = tf.nn.bias_add(conv, biases)
            self.enc_conv1_1 = tf.nn.relu(out, name=scope)
            self.parameters += [kernel, biases]

        # conv1_2
        with tf.name_scope('enc_conv1_2') as scope:
            kernel = tf.Variable(tf.truncated_normal([3, 3, 32, 32], dtype=tf.float32, stddev=2.0/np.sqrt(144 + 64) ), name='weights')
            conv = tf.nn.conv2d(self.enc_conv1_1, kernel, [1, 1, 1, 1], padding='SAME')
            biases = tf.Variable(tf.constant(0.1, shape=[32], dtype=tf.float32), trainable=True, name='biases')
            out = tf.nn.bias_add(conv, biases)
            self.enc_conv1_2 = tf.nn.relu(out, name=scope)
            self.parameters += [kernel, biases]

        # pool1
        with tf.name_scope('enc_pooling1'):
            self.pool1 = tf.nn.max_pool(self.enc_conv1_2,
                                        ksize=[1, 2, 2, 1],
                                        strides=[1, 2, 2, 1],
                                        padding='SAME',
                                        name='enc_pool1')

        # conv2_1
        with tf.name_scope('enc_conv2_1') as scope:
            kernel = tf.Variable(tf.truncated_normal([3, 3, 32, 64], dtype=tf.float32, stddev=2.0/np.sqrt(144 + 16) ), name='weights')
            conv = tf.nn.conv2d(self.pool1, kernel, [1, 1, 1, 1], padding='SAME')
            biases = tf.Variable(tf.constant(0.1, shape=[64], dtype=tf.float32), trainable=True, name='biases')
            out = tf.nn.bias_add(conv, biases)
            self.enc_conv2_1 = tf.nn.relu(out, name=scope)
            self.parameters += [kernel, biases]

        # conv2_2
        with tf.name_scope('enc_conv2_2') as scope:
            kernel = tf.Variable(tf.truncated_normal([3, 3, 64, 64], dtype=tf.float32, stddev=2.0/np.sqrt(144+16)), name='weights')
            conv = tf.nn.conv2d(self.enc_conv2_1, kernel, [1, 1, 1, 1], padding='SAME')
            biases = tf.Variable(tf.constant(0.1, shape=[64], dtype=tf.float32), trainable=True, name='biases')
            out = tf.nn.bias_add(conv, biases)
            self.enc_conv2_2 = tf.nn.relu(out, name=scope)
            self.parameters += [kernel, biases]

        # pool2
        with tf.name_scope('enc_pooling2'):
            self.pool2 = tf.nn.max_pool(self.enc_conv2_2,
                                        ksize=[1, 2, 2, 1],
                                        strides=[1, 2, 2, 1],
                                        padding='SAME',
                                        name='enc_pool2')

        prev_dim = int(np.prod(self.pool2.get_shape()[1:]))

        pool2_flat = tf.reshape(self.pool2, [-1,prev_dim])
        # fc1
        with tf.name_scope('enc_z_mean') as scope:
            # the total number of features extracted per input image
            fc_w = tf.Variable(tf.truncated_normal([prev_dim, self.LATENTDIM], dtype=tf.float32, stddev=1.0/np.sqrt(prev_dim + self.LATENTDIM)), name='weights')
            fc_b = tf.Variable(tf.constant(0.1, shape=[self.LATENTDIM], dtype=tf.float32), trainable=True, name='biases')
            self.z_mean = tf.nn.bias_add(tf.matmul(pool2_flat, fc_w), fc_b)
            self.parameters += [fc_w, fc_b]

        with tf.name_scope('enc_z_variance') as scope:
            # the total number of features extracted per input image
            fc_w = tf.Variable(tf.truncated_normal([prev_dim, self.LATENTDIM], dtype=tf.float32, stddev=2.0/np.sqrt(prev_dim + self.LATENTDIM)), name='weights')
            fc_b = tf.Variable(tf.constant(0.1, shape=[self.LATENTDIM], dtype=tf.float32), trainable=True, name='biases')
            self.z_log_sigma_sq = tf.nn.bias_add(tf.matmul(pool2_flat, fc_w), fc_b)
            self.parameters += [fc_w, fc_b]

    def _decoder_network(self):
        # the size that ends up at the encoder is 8 x 8 x 64
        with tf.name_scope('dec_fc'):
            fc_g_w = tf.Variable(tf.truncated_normal([self.LATENTDIM,4096], dtype=tf.float32, stddev=1.0/np.sqrt(self.LATENTDIM + 2048)), name='weights')
            fc_g_b = tf.Variable(tf.constant(0.1, shape=[4096], dtype=tf.float32), trainable=True, name='biases')
            a_1 = tf.nn.bias_add(tf.matmul(self.z, fc_g_w), fc_g_b)
            self.g_1 = tf.nn.relu(a_1)
            self.parameters += [fc_g_w, fc_g_b]

        with tf.name_scope('dec_reshape'):
            g_1_images = tf.reshape(self.g_1, [-1,8,8,64])

        # scale up to size 16 x 16 x 64
        resized_1 = None
        with tf.name_scope('dec_resize1'):
            if tf.__version__ == '0.12.0-rc0' or tf.__version__=='0.11.0':
                resized_1 = tf.image.resize_images(g_1_images, [16, 16], method=tf.image.ResizeMethod.BILINEAR)
            else:
                resized_1 = tf.image.resize_images(g_1_images, 16, 16, method=tf.image.ResizeMethod.BILINEAR)

        # conv1_1
        with tf.name_scope('dec_conv1_1') as scope:
            kernel = tf.Variable(tf.truncated_normal([3, 3, 64, 32], dtype=tf.float32, stddev=2.0/np.sqrt(288 + 16)), name='weights')
            conv = tf.nn.conv2d(resized_1, kernel, [1, 1, 1, 1], padding='SAME')
            biases = tf.Variable(tf.constant(0.0, shape=[32], dtype=tf.float32), trainable=True, name='biases')
            out = tf.nn.bias_add(conv, biases)
            self.dec_conv1_1 = tf.nn.relu(out, name=scope)
            self.parameters += [kernel, biases]

        with tf.name_scope('dec_conv1_2') as scope:
            kernel = tf.Variable(tf.truncated_normal([3, 3, 32, 32], dtype=tf.float32, stddev=2.0/np.sqrt(144 + 16)  ), name='weights')
            conv = tf.nn.conv2d(self.dec_conv1_1, kernel, [1, 1, 1, 1], padding='SAME')
            biases = tf.Variable(tf.constant(0.0, shape=[32], dtype=tf.float32), trainable=True, name='biases')
            out = tf.nn.bias_add(conv, biases)
            self.dec_conv1_2 = tf.nn.relu(out, name=scope)
            self.parameters += [kernel, biases]


        # scale up to size 32 x 32 x 32
        resized_2 = None
        with tf.name_scope('dec_resize2'):
            if tf.__version__ == '0.12.0-rc0' or tf.__version__=='0.11.0':
                resized_2 = tf.image.resize_images(self.dec_conv1_2, [32, 32], method=tf.image.ResizeMethod.BILINEAR)
            else:
                resized_2 = tf.image.resize_images(self.dec_conv1_2, 32, 32, method=tf.image.ResizeMethod.BILINEAR)

        with tf.name_scope('dec_conv2_1') as scope:
            kernel = tf.Variable(tf.truncated_normal([3, 3, 32, 3], dtype=tf.float32, stddev=2.0/np.sqrt(144 + 3)), name='weights')
            conv = tf.nn.conv2d(resized_2, kernel, [1, 1, 1, 1], padding='SAME')
            biases = tf.Variable(tf.constant(0.0, shape=[3], dtype=tf.float32), trainable=True, name='biases')
            out = tf.nn.bias_add(conv, biases)
            self.dec_conv2_1 = tf.nn.relu(out, name=scope)
            self.parameters += [kernel, biases]

        with tf.name_scope('dec_conv2_2') as scope:
            kernel = tf.Variable(tf.truncated_normal([3, 3, 3, 3], dtype=tf.float32, stddev=2.0/np.sqrt(27 + 3)), name='weights')
            conv = tf.nn.conv2d(self.dec_conv2_1, kernel, [1, 1, 1, 1], padding='SAME')
            biases = tf.Variable(tf.constant(0.0, shape=[3], dtype=tf.float32), trainable=True, name='biases')
            out = tf.nn.bias_add(conv, biases)
            self.dec_conv2_2 = out
            self.parameters += [kernel, biases]

        with tf.name_scope('dec_output'):
            self.x_reconstr_mean = tf.sigmoid(self.dec_conv2_2)

    def _make_log_information(self):

        self.TIME_STAMP = get_time_stamp()
        self.LOG_DIR_ROOT = 'my_logs_dir'
        if not os.path.exists(self.LOG_DIR_ROOT):
            os.makedirs(self.LOG_DIR_ROOT)
        self.LOG_DIR   = '{}/{}'.format(self.LOG_DIR_ROOT,self.TIME_STAMP)
        if not os.path.exists(self.LOG_DIR):
            os.makedirs(self.LOG_DIR)
        self.MODEL_DIR = '{}/{}'.format(self.LOG_DIR,'model_checkpoint')
        if not os.path.exists(self.MODEL_DIR):
            os.makedirs(self.MODEL_DIR)
        self.TEMP_MODEL_DIR = '{}/{}'.format(self.MODEL_DIR,'temp')
        if not os.path.exists(self.TEMP_MODEL_DIR):
            os.makedirs(self.TEMP_MODEL_DIR)
        self.RESULTS_DIR = '{}/{}'.format(self.LOG_DIR,'results')
        if not os.path.exists(self.RESULTS_DIR):
            os.makedirs(self.RESULTS_DIR)

        self.check_point_file = '{}/model.ckpt'.format(self.MODEL_DIR)

    def _make_summaries(self):
        tf.scalar_summary('z_log_sigma_squared_min', tf.reduce_min( self.z_log_sigma_sq ) )
        tf.scalar_summary('z_log_sigma_squared_max', tf.reduce_max( self.z_log_sigma_sq ) )

        self.merged_summaries = tf.merge_all_summaries()

    def train(self, num_epochs_to_display=1):
        if self.datasets is None:
            print('loading datasets')
            self._load_datasets(num_train = self.NUM_TRAIN)

        tc = 0
        fc = 0
        lc = 0
        pc = 0

        costs = {}
        costs['latent'] = []
        costs['pixel'] = []
        costs['total'] = []

        current_lr = 1e-4

        init  = tf.initialize_all_variables()
        saver = tf.train.Saver(self.parameters)

        current_epoch_cost = 0
        current_rec_cost = 0
        current_lat_cost = 0
        current_pix_cost = 0

        ITERATIONS_PER_EPOCH = int(self.NUM_TRAIN/self.BATCH_SIZE)

        with tf.Session() as sess:
            sess.run(init)

            batch_images = self.datasets.train.next_batch(self.BATCH_SIZE)[0]

            t0 = time.time()

            eps = np.random.normal(loc=0.0, scale=1.0, size=(self.BATCH_SIZE,self.LATENTDIM))
            tc, lc, pc, run_summary = sess.run([self.cost, self.latent_loss_mean, self.pixel_loss_mean, self.merged_summaries], feed_dict={self.x_placeholder: batch_images, self.eps_placeholder: eps})

            # this is the initial state
            self.summary_writer.add_summary(run_summary,-1)

            # Append them to lists
            costs['total'].append(fc)
            costs['pixel'].append(pc)
            costs['latent'].append(lc)

            t1 = time.time()
            print('Initial Cost: {:2f}  = {:.2f} L + {:.2f} P -- time taken {:.2f}'.format(tc, lc, pc, t1-t0))

            t0 = t1

            # Train for several epochs
            for epoch in range(self.NUM_EPOCS):

                if self.DECAY_LR:
                    if epoch != 0 and epoch % self.NUM_EPOCHS_TO_DECAY_LR == 0:
                        current_lr /= 2
                        current_lr = max(current_lr, 1e-6)
                print ("learning rate : {}".format(current_lr))

                for i in range(ITERATIONS_PER_EPOCH):
                    # pick a mini batch
                    batch_images = self.datasets.train.next_batch(self.BATCH_SIZE)[0]
                    eps = np.random.normal(loc=0.0, scale=1.0, size=(self.BATCH_SIZE,self.LATENTDIM))

                    _, tc, lc, pc, run_summary = sess.run([self.train_step, self.cost, self.latent_loss_mean, self.pixel_loss_mean, self.merged_summaries],feed_dict={self.x_placeholder:batch_images, self.eps_placeholder: eps, self.lr_placeholder: current_lr})

                    current_epoch_cost += tc
                    current_lat_cost += lc
                    current_pix_cost += pc

                # for displaying costs etc -------------------------------------
                current_epoch_cost /= ITERATIONS_PER_EPOCH # average it over the iterations
                current_lat_cost /= ITERATIONS_PER_EPOCH
                current_pix_cost /= ITERATIONS_PER_EPOCH
                # create a summary object for writing epoch costs
                summary = tf.Summary()
                summary.value.add(tag='total cost for epoch',simple_value=current_epoch_cost)
                summary.value.add(tag='latent cost for epoch',simple_value=current_lat_cost)
                summary.value.add(tag='pixel cost for epoch',simple_value=current_pix_cost)
                self.summary_writer.add_summary(summary,epoch)
                self.summary_writer.add_summary(run_summary,epoch)
                costs['total'].append(current_epoch_cost)
                costs['latent'].append(current_lat_cost)
                costs['pixel'].append(current_pix_cost)
                # --------------------------------------------------------------


                # print stats --------------------------------------------------
                if epoch % num_epochs_to_display == 0:
                    t1 = time.time()
                    print(' epoch: {}/{} -- cost {:.2f} = {:.2f} L + {:.2f} P -- time taken {:.2f}'.format(epoch+1,self.NUM_EPOCS,current_epoch_cost, current_lat_cost,current_pix_cost, t1-t0))
                    # Reset the timer
                    t0 = t1
                # --------------------------------------------------------------

                # Reset the costs for next epoch -------------------------------
                current_epoch_cost = 0
                current_rec_cost = 0
                current_lat_cost = 0
                current_pix_cost = 0
                # --------------------------------------------------------------

                if (epoch+1) % self.SAVE_EPOCS == 0 and epoch != 0 and epoch != (self.NUM_EPOCS-1):
                    #Saves the weights (not the graph)
                    temp_checkpoint_file = '{}/epoch_{}.ckpt'.format(self.TEMP_MODEL_DIR,epoch)
                    save_path = saver.save(sess, temp_checkpoint_file)
                    print("Epoch : {} Model saved in file: {}".format(epoch, save_path))
                    t0 = time.time()

            #Saves the weights (not the graph)
            save_path = saver.save(sess, self.check_point_file)
            t1 = time.time()
            print("Model saved")

    def generate(self, z = None, n = 1, checkpoint = None):
        """ Generate data from the trained model
        If z is not defined, will feed random normal as input
        """
        if z is None:
            z = np.random.random(size=(n,self.LATENTDIM))
        if checkpoint is None:
            checkpoint = self.checkpoint_file

        saver = tf.train.Saver(self.parameters)
        with tf.Session() as sess:
            saver.restore(sess, checkpoint)
            generated_images = sess.run((self.x_reconstr_mean),feed_dict={self.z: z})

        return generated_images

    def reconstruct_images(self, h_num = 5, v_num = 2):

        # show target features and estimated features
        num_visualize = h_num * v_num

        num_visualize = min(self.NUM_TRAIN,num_visualize)

        saver = tf.train.Saver(self.parameters)

        with tf.Session() as sess:
            saver.restore(sess, self.check_point_file)
            print("Model restored.")

            sample_images = self.datasets.train.next_batch(num_visualize)[0]

            eps = np.random.normal(loc=0.0, scale=1.0, size=(num_visualize,self.LATENTDIM))
            reconstructed_images  = sess.run((self.x_reconstr_mean), feed_dict={self.x_placeholder: sample_images, self.eps_placeholder: eps})

            # Reconstruct images
            plt.figure(figsize=(10, 6))
            for i in range(num_visualize):
                plt.subplot(2*v_num, h_num, i + 1)
                plt.imshow(sample_images[i], vmin=0, vmax=1,  interpolation='none',cmap=plt.get_cmap('gray'))
                plt.title("Test input")
                plt.axis('off')

                plt.subplot(2*v_num, h_num, num_visualize + i +1 )
                plt.imshow(reconstructed_images[i], vmin=0, vmax=1,  interpolation='none',cmap=plt.get_cmap('gray'))
                plt.title("Reconstruction")
                plt.axis('off')
            # plt.tight_layout()
            plt.savefig('{}/cifar-reconstruction-ld{}-bs{}-ep{}-lr{}.pdf'.format(self.RESULTS_DIR, self.LATENTDIM, self.BATCH_SIZE, self.NUM_EPOCS, self.LEARNING_RATE*1e5))
            plt.close()
        ## ============= S8 Ends ==================

        print('logs have been written to: {}'.format(self.LOG_DIR))