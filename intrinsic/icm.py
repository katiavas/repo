import torch as T
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import os


class Encoder(nn.Module):
    def __init__(self, input_dims, feature_dim=288):
        super(Encoder, self).__init__()
        
        self.conv1 = nn.Conv2d(input_dims[0], 32, (3, 3), stride=2, padding=1)
        self.conv2 = nn.Conv2d(32, 32, (3, 3), stride=2, padding=1)
        self.conv3 = nn.Conv2d(32, 32, (3, 3), stride=2, padding=1)
        self.conv4 = nn.Conv2d(32, 32, (3, 3), stride=2, padding=1)
        
    def forward(self, img):
        enc = F.elu(self.conv1(img))
        enc = F.elu(self.conv2(enc))
        enc = F.elu(self.conv3(enc))
        enc = self.conv4(enc)
        # [T, 32, 3, 3] to [T, 288]
        enc_flatten = T.flatten(enc, start_dim=1)
        # conv = enc.view(enc.size()[0], -1).to(T.float)
        return enc_flatten

    '''def __init__(self, input_dims, feature_dim=288):
        super(Encoder, self).__init__()

        self.conv1 = nn.Conv2d(input_dims[0], 32, (3, 3), stride=2, padding=1)
        self.conv2 = nn.Conv2d(32, 32, (3, 3), stride=2, padding=1)
        self.conv3 = nn.Conv2d(32, 32, (3, 3), stride=2, padding=1)
        self.conv4 = nn.Conv2d(32, 32, (3, 3), stride=2, padding=1)

        shape = self.get_conv_out(input_dims)
        # Layer that will extract the features
        self.fc1 = nn.Linear(shape, feature_dim)

    def get_conv_out(self, input_dims):
        img = T.zeros(1, *input_dims)
        x = self.conv1(img)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.conv4(x)
        shape = x.size()[0] * x.size()[1] * x.size()[2] * x.size()[3]
        # return int(np.prod(x.size()))
        return shape

    def forward(self, img):
        enc = F.elu(self.conv1(img))
        enc = F.elu(self.conv2(enc))
        enc = F.elu(self.conv3(enc))
        enc = self.conv4(enc)
        # [T, 32, 3, 3] to [T, 288]
        enc_flatten = T.flatten(enc, start_dim=1)
        # conv = enc.view(enc.size()[0], -1).to(T.float)
        features = self.fc1(enc_flatten)

        return features'''


class ICM(nn.Module):
    def __init__(self, input_dims, n_actions=4, alpha=0.1, beta=0.2, feature_dims=288):
        super(ICM, self).__init__()
        self.alpha = alpha
        self.beta = beta
        self.encoder = Encoder(input_dims)

        self.inverse = nn.Linear(feature_dims * 2, 256)
        self.pi_logits = nn.Linear(256, n_actions)

        self.dense1 = nn.Linear(feature_dims + 1, 256)
        self.phi_hat_new = nn.Linear(256, feature_dims)

        self.icm = ICM(input_dims)

        device = T.device('cpu')
        self.to(device)

    ''' The prediction module takes in a state St and action at and produces a prediction for the subsequent state S t+1 '''

    def forward(self, obs, new_obs, action):
        phi = self.encoder(obs)
        with T.no_grad():
            phi_new = self.encoder(new_obs)

        phi = phi.to(T.float)
        phi_new = phi_new.to(T.float)

        ''' We have to concatenate a state and action and pass it through the inverse layer'''
        inverse = self.inverse(T.cat([phi, phi_new], dim=1))
        pi_logits = self.pi_logits(inverse)

        # from [T] to [T, 1]
        action = action.reshape((action.size()[0], 1))
        forward_input = T.cat([phi, action], dim=1)
        dense = self.dense1(forward_input)
        phi_hat_new = self.phi_hat_new(dense)

        return phi_new, pi_logits, phi_hat_new

    def save_models(self):
        # self.actor_critic.save(self.checkpoint_file)
        np.save(os.path.join('./', 'icm'), self.icm)
        print('... saving models ...')


    '''This prediction along with the true next state are passed to a mean-squared error (or some other error) function 
    which produces the prediction error'''

    def calc_loss(self, states, new_states, actions):
        # don't need [] b/c these are lists of states
        states = T.tensor(states, dtype=T.float)
        actions = T.tensor(actions, dtype=T.float)
        new_states = T.tensor(new_states, dtype=T.float)

        phi_new, pi_logits, phi_hat_new = self.forward(states, new_states, actions)

        inverse_loss = nn.CrossEntropyLoss()
        L_I = (1 - self.beta) * inverse_loss(pi_logits, actions.to(T.long))

        forward_loss = nn.MSELoss()
        L_F = self.beta * forward_loss(phi_hat_new, phi_new)

        intrinsic_reward = self.alpha * 0.5 * ((phi_hat_new - phi_new).pow(2)).mean(dim=1)
        return intrinsic_reward, L_I, L_F
