import numpy as np
import tensorflow as tf
from vae_rahan import *
import argparse

np.random.seed(0)
tf.set_random_seed(0)

parser = argparse.ArgumentParser()

parser.add_argument('--latent_dimensions', type=int, default=5, help='latent dimensions')
parser.add_argument('--num_epochs', type=int, default=1500, help='number of epochs')
parser.add_argument('--learning_rate', type=float, default=1e-2, help='learning rate')
parser.add_argument('--num_epochs_to_decay_lr', type=int, default=0, help='number of epochs to decay learning rate')
parser.add_argument('--num_train', type=int, default=1, help='number of samples to train on')
parser.add_argument('--batch_size', type=int, default=1, help='batch size')
parser.add_argument('--save_epochs', type=int, default=1000, help='number of epochs to save temporary checkpoint')

args = parser.parse_args()

our_vae = VariationalAutoencoder(latent_dimensions = args.latent_dimensions,
				num_epochs = args.num_epochs,
				learning_rate = args.learning_rate,
				num_epochs_to_decay_lr = args.num_epochs_to_decay_lr,
				num_train = args.num_train,
				batch_size = args.batch_size,
				save_epochs = args.save_epochs)

our_vae.print_setting()

our_vae.train()

our_vae.reconstruct_images()