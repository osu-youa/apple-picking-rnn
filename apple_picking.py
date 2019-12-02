import glob

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Conv1D, Flatten, Dropout, MaxPooling1D, GlobalAveragePooling1D, LSTM
from sklearn.utils import shuffle

import random
import numpy as np
import pandas as pd 

import math
import matplotlib
import matplotlib.pyplot as plt

import os
import sys

ROOT = os.path.dirname(os.path.realpath(__file__))

class ApplePicking:

    def __init__(self, window_size, train_dir='training_data', test_dir='testing_data', model_folder='models', val_split=0.10):
        self.train_dir = os.path.join(ROOT, train_dir)
        self.model_dir = os.path.join(ROOT, model_folder)
        
        self.window_size = window_size
        self.INPUT_COLS = ['/manipulator_wrench.fx', '/manipulator_wrench.fy', '/manipulator_wrench.fz', '/manipulator_wrench.tx', '/manipulator_wrench.ty', '/manipulator_wrench.tz',  
                           '/joint_states.shoulder_lift_joint', '/joint_states.elbow_joint', '/joint_states.wrist_1_joint', '/joint_states.wrist_2_joint', '/joint_states.wrist_3_joint']

        self.OUTPUT_COLS = ['/ground_truth.x', '/ground_truth.y', '/ground_truth.z']
        self.train, self.validation = self.load_all_data(val_split, is_smooth=False)
        
        test_folder = os.path.join(ROOT, test_dir)
        test_files = [file for file in glob.glob(os.path.join(test_folder, "*.csv"), recursive=False)]
        test_X, test_Y = self.get_data(test_files, is_smooth=False)
        self.test = (test_X, test_Y)

    def add_force_mag_data(self, row):
        fx = row['/wrench.fx']
        fy = row['/wrench.fy']
        fz = row['/wrench.fz']
        f_mag = math.sqrt(fx**2 + fy**2 + fz**2)
        return f_mag

    def adjust_force_data(self, df):
        force_cols = ['/manipulator_wrench.fx', '/manipulator_wrench.fy', '/manipulator_wrench.fz', '/manipulator_wrench.tx', '/manipulator_wrench.ty', '/manipulator_wrench.tz']
        subset = df[force_cols]
        tared = subset - subset.iloc[0]
        df[force_cols] = tared
        # df['force_mag'] = (tared ** 2).sum(axis=1) ** 0.5
        df = df.iloc[1:].reset_index(drop=True)
        return df

    def format_data(self, df):
        n_df = len(df) - self.window_size
        X = []
        Y = []
        for i in range(0, n_df):
            seq_X = df.iloc[i: i+self.window_size]
            seq_Y = seq_X.iloc[-1]
            x = seq_X[self.INPUT_COLS].values
            y = seq_Y[self.OUTPUT_COLS].values
            X.append(x)
            Y.append(y)
        return X, Y

    def smooth_data(self, df, window=3):
        ALL_COLS = self.INPUT_COLS + self.OUTPUT_COLS
        df = df[ALL_COLS].rolling(window, center=True).mean()
        df = df.dropna().reset_index(drop=True)
        return df

    def get_data(self, files_list, is_smooth):
        X_data = []
        Y_data = []
        mode_col = '/mode./mode'
        for file in files_list:
            temp_df = pd.read_csv(file)
            temp_df = self.adjust_force_data(temp_df)
            
            # Taking only the mode 3 columns
            temp_df = temp_df.loc[temp_df[mode_col] == 3]
            temp_df = temp_df.dropna().reset_index(drop=True)

            if is_smooth == True:
                print("Smothing...")
                temp_df = self.smooth_data(temp_df) # Smoothing using moving average filter

            temp_X, temp_Y = self.format_data(temp_df)
            X_data = X_data + temp_X
            Y_data = Y_data + temp_Y

        X_data = np.array(X_data, dtype=np.float64)
        Y_data = np.array(Y_data, dtype=np.float64)
        return X_data, Y_data

    def load_all_data(self, val_split, is_smooth=False):
        print ("Loading Data ...")

        all_files = [file for file in glob.glob(os.path.join(self.train_dir, "*.csv"), recursive=False)]
        random.shuffle(all_files)

        split_idx = int(round(val_split*len(all_files)))
        
        val_files = all_files[0: split_idx]
        train_files = all_files[split_idx: ]
        
        train_X, train_Y = self.get_data(train_files, is_smooth)
        val_X, val_Y = self.get_data(val_files, is_smooth)

        print("\nNumber of Train fies: ", len(train_files))
        print("Train data shape: {}, {}\n".format(train_X.shape, train_Y.shape))
        print("Number of Val fies: ", len(val_files))
        print("Test data shape: {}, {}\n".format(val_X.shape, val_Y.shape))
        return (train_X, train_Y), (val_X, val_Y)

    def perf_nnet_conv1D(self, feature_dim, output_dim, model_path):
        model = Sequential()
        model.add(Conv1D(32, 3, activation='relu', input_shape=(self.window_size, feature_dim)))
        model.add(Conv1D(64, 3, activation='relu'))
        # model.add(MaxPooling1D(2))
        model.add(Dropout(0.2))

        model.add(Conv1D(128, 3, activation='relu'))
        # model.add(Conv1D(128, 3, activation='relu'))
        model.add(MaxPooling1D(2))
        # model.add(GlobalAveragePooling1D())
        model.add(Dropout(0.2))

        model.add(Flatten())
        model.add(Dense(output_dim, activation='linear'))
        model.compile(loss='mae', optimizer="adam", metrics=['mae', 'accuracy'])
        print(model.summary())
        model.save(model_path)
        return model

    def perf_nnet_LSTM(self, feature_dim, output_dim, model_path):
        model = Sequential()
        model.add(LSTM(32, return_sequences=True, input_shape=(self.window_size, feature_dim)))
        # model.add(LSTM(hidden_neurons, return_sequences=True))
        model.add(LSTM(32))
        model.add(Dense(output_dim, activation='linear'))
        model.compile(loss='mae', optimizer="adam", metrics=['mae', 'accuracy'])
        print(model.summary())
        model.save(model_path)
        return model

    def perf_nnet_ann(self, feature_dim, output_dim, model_path):
        model = Sequential()
        model.add(Dense(32, activation='relu', input_shape=(feature_dim,)))
        model.add(Dropout(0.2))
        model.add(Dense(64, activation='relu'))
        model.add(Dropout(0.2))
        model.add(Dense(output_dim, activation='linear'))
        model.compile(loss='mae', optimizer="adam", metrics=['mae', 'accuracy'])
        print(model.summary())
        model.save(model_path)
        return model

    def train_network(self, net, n_epoch=1000, is_restore=False, clear_tmp=True):
        feature_dim = len(self.INPUT_COLS)
        output_dim = len(self.OUTPUT_COLS)
        
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)

        # clear tmp directory to save disk space
        logdir = "/tmp/tflearn_logs/"
        if clear_tmp == True and os.path.exists(logdir): 
            os.system("rm -r " + logdir + "*")

        model_name = 'force_vec_pred_' + net + '_ws' + str(self.window_size) + '_fdim' + str(feature_dim)  # + '_e' + str(n_epoch)
        model_path = os.path.join(self.model_dir, '{}.h5'.format(model_name))
        tensorboard_cb = tf.keras.callbacks.TensorBoard(log_dir=logdir, histogram_freq=1)
        checkpoint_cb = tf.keras.callbacks.ModelCheckpoint(filepath=model_path, verbose=1, save_best_only=True)

        (train_inputs, train_labels) = self.train
        (val_inputs, val_labels) = self.validation

        if net == 'ANN':
            train_inputs = train_inputs.reshape(-1, feature_dim)
            val_inputs = val_inputs.reshape(-1, feature_dim)
            print (train_inputs.shape, val_inputs.shape)
            self.model = self.perf_nnet_ann(feature_dim, output_dim, model_path)
            shuffle = True

        elif net == 'Conv1D':
            self.model = self.perf_nnet_conv1D(feature_dim, output_dim, model_path)
            shuffle = True

        elif net == 'LSTM':
            self.model = self.perf_nnet_LSTM(feature_dim, output_dim, model_path)
            shuffle = False

        if is_restore == True:
            self.model = keras.models.load_model(model_path)
            shuffle = True

        self.model.fit(train_inputs, train_labels, epochs=n_epoch, verbose=1, callbacks=[tensorboard_cb, checkpoint_cb], validation_data=(val_inputs, val_labels), shuffle=shuffle)

    def predict_network(self, net, model_name, inputs):
        if net =='ANN':
            inputs = inputs.reshape(inputs.shape[0], inputs.shape[2])
        model_path = os.path.join(self.model_dir, '{}.h5'.format(model_name))
        self.model = keras.models.load_model(model_path)
        predictions = self.model.predict(inputs)
        return predictions

    def orientation_error(self, targets, predictions):
        orientation_error = []
        for i in range(len(predictions)):
            vec_1 = predictions[i]
            vec_1 = vec_1/np.linalg.norm(vec_1)

            vec_2 = targets[i]
            vec_2 = vec_2/np.linalg.norm(vec_2)
            radian = np.arccos(np.clip(np.dot(vec_1, vec_2), -1.0, 1.0))
            theta = (180.0/math.pi)*radian
            orientation_error.append(theta)
        print(np.shape(orientation_error))
        return orientation_error

if __name__ == '__main__':
    
    mode = 'train_mode'
    net = 'LSTM'
    window_size = 5

    if len(sys.argv) > 1:
        mode = sys.argv[1]

    if len(sys.argv) > 2:
        net = sys.argv[2]

    apple_picking_obj = ApplePicking(window_size=window_size)

    if mode == 'train_mode':
        apple_picking_obj.train_network(net=net, is_restore=False)

    elif mode == 'predict_mode':
        # model_name = 'force_vec_pred_ws10_fdim11_Conv1D'
        model_name =  'force_vec_pred_Conv1D_ws10_fdim11'

        output_base = os.path.join(ROOT, 'output_{}_{}.png')

        data_label = 'Training'
        
        if data_label == 'Testing':
            inputs, outputs = apple_picking_obj.test

        elif data_label == 'Training':
            inputs, outputs = apple_picking_obj.validation

        inputs, outputs = shuffle(inputs, outputs, random_state=0)
        predictions = apple_picking_obj.predict_network('Conv1D', model_name, inputs)
        orientation_error = apple_picking_obj.orientation_error(outputs, predictions)
        
        orientation_arr = np.array(orientation_error)
        print("Maximum Ang Error: ", np.max(orientation_arr))
        print("Minimum Ang Error: ", np.min(orientation_arr))
        print("Average Ang Error: ", np.mean(orientation_arr))
        print("Std Deviation Ang: ", np.std(orientation_arr))

        # Plotting the error in the orientation
        plt.clf()
        plt.plot(orientation_error, color='r')
        
        plt.title('Orientation Error in degrees', fontsize=35)
        plt.xlabel("Time Steps (0.1s)", fontsize=25)
        plt.ylabel("Orrientation Error (deg)", fontsize=25)
        plt.ylim(0.0, 20.0)
        plt.show()
        # plt.savefig(output_base.format(data_label.lower(), label.lower()))
        
        # Plotting individual X,Y,Z components
        for idx, label in [(0, 'X'), (1, 'Y'), (2, 'Z')]:
            plt.clf()
            plt.plot(outputs[:, idx], label=label, color='r')
            plt.plot(predictions[:, idx], label='{} (pred)'.format(label), color='g')
            plt.legend()
            plt.title('{} Data - {} coord'.format(data_label, label))
            # plt.savefig(output_base.format(data_label.lower(), label.lower()))
            # plt.show()

        # for data_label, dataset in [['Training', random.choice(apple_picking_obj.train)], ['Validation', random.choice(apple_picking_obj.test)]]:
        #     # Test a data set
        #     inputs, outputs = apple_picking_obj.train
        #     predictions = apple_picking_obj.predict_network(model_name, inputs)

        #     for idx, label in [(0, 'X'), (1, 'Y'), (2, 'Z')]:
        #         plt.clf()
        #         plt.plot(outputs[:, idx], label=label, color='r')
        #         plt.plot(predictions[:, idx], label='{} (pred)'.format(label), color='g')
        #         plt.legend()
        #         plt.title('{} Data - {} coord'.format(data_label, label))
        #         plt.show()
        #         plt.savefig(output_base.format(data_label.lower(), label.lower()))
