
from __future__ import division
from keras.utils.vis_utils import plot_model
import random
import pprint
import sys
import time
import numpy as np
from optparse import OptionParser
import pickle
import os

import tensorflow as tf
from keras import backend as K
from keras.optimizers import Adam, SGD, RMSprop
from keras.layers import Input
from keras.models import Model
from keras_interactnet import config, data_generators
from keras_interactnet import losses as losses
import keras_interactnet.roi_helpers as roi_helpers
from keras.utils import generic_utils
from keras.callbacks import TensorBoard

def write_log(callback, names, logs, batch_no):
    for name, value in zip(names, logs):
        summary = tf.Summary()
        summary_value = summary.value.add()
        summary_value.simple_value = value
        summary_value.tag = name
        callback.writer.add_summary(summary, batch_no)
        callback.writer.flush()

sys.setrecursionlimit(40000)

parser = OptionParser()

parser.add_option("-p", "--path", dest="train_path", help="Path to training data.")
parser.add_option("-o", "--parser", dest="parser", help="Parser to use. One of simple or pascal_voc",
                  default="simple")
parser.add_option("-n", "--num_rois", dest="num_rois", help="Number of RoIs to process at once.", default=128)
parser.add_option("--network", dest="network", help="Base network to use. Supports vgg or resnet50.", default='resnet50')
parser.add_option("--hf", dest="horizontal_flips", help="Augment with horizontal flips in training. (Default=false).", action="store_true", default=False)
parser.add_option("--vf", dest="vertical_flips", help="Augment with vertical flips in training. (Default=false).", action="store_true", default=False)
parser.add_option("--rot", "--rot_90", dest="rot_90", help="Augment with 90 degree rotations in training. (Default=false).",
                  action="store_true", default=False)
parser.add_option("--num_epochs", dest="num_epochs", help="Number of epochs.", default=2000)
parser.add_option("--config_filename", dest="config_filename",
                  help="Location to store all the metadata related to the training (to be used when testing).",
                  default="config.pickle")
parser.add_option("--output_weight_path", dest="output_weight_path", help="Output path for weights.", default='./model_frcnn.hdf5')
parser.add_option("--input_weight_path", dest="input_weight_path", help="Input path for weights. If not specified, will try to load default weights provided by keras.")

(options, args) = parser.parse_args()

if not options.train_path:   # if filename is not given
    parser.error('Error: path to training data must be specified. Pass --path to command line')

if options.parser == 'pascal_voc':
    from keras_interactnet.pascal_voc_parser import get_data
elif options.parser == 'simple':
    #from keras_interactnet.vcoco.simple_parser import get_data
    a = 1
else:
    raise ValueError("Command line option parser must be one of 'pascal_voc' or 'simple'")

# pass the settings from the command line, and persist them in the config object
C = config.Config()

C.use_horizontal_flips = bool(options.horizontal_flips)
C.use_vertical_flips = bool(options.vertical_flips)
C.rot_90 = bool(options.rot_90)

C.model_path = options.output_weight_path
C.num_rois = int(options.num_rois)

num_rois_h = 4

if options.network == 'vgg':
    C.network = 'vgg'
    from keras_interactnet import vgg as nn
elif options.network == 'resnet50':
    from keras_interactnet import resnet as nn
    C.network = 'resnet50'
elif options.network == 'xception':
    from keras_interactnet import xception as nn
    C.network = 'xception'
elif options.network == 'inception_resnet_v2':
    from keras_interactnet import inception_resnet_v2 as nn
    C.network = 'inception_resnet_v2'
else:
    print('Not a valid model')
    raise ValueError

# check if weight path was passed via command line
if options.input_weight_path:
    C.base_net_weights = options.input_weight_path
else:
    # set the path to weights based on backend and model
    C.base_net_weights = nn.get_weight_path()
'''
all_imgs, classes_count, class_mapping, actions_count, action_mapping = get_data(options.train_path)


pickle_out = open("classes_count_inet.pickle","wb") ;pickle.dump(classes_count, pickle_out) ;pickle_out.close();
pickle_out = open("class_mapping_inet.pickle","wb") ;pickle.dump(class_mapping, pickle_out) ;pickle_out.close();
pickle_out = open("actions_count_inet.pickle","wb") ;pickle.dump(actions_count, pickle_out) ;pickle_out.close();
pickle_out = open("action_mapping_inet.pickle","wb") ;pickle.dump(action_mapping, pickle_out) ;pickle_out.close();
pickle_out = open("all_imgs_inet.pickle","wb") ;pickle.dump(all_imgs, pickle_out) ;pickle_out.close();

'''
pickle_in = open("classes_count_inet.pickle","rb") ;classes_count=pickle.load(pickle_in)
pickle_in = open("class_mapping_inet.pickle","rb") ;class_mapping=pickle.load(pickle_in)
pickle_in = open("actions_count_inet.pickle","rb") ;actions_count=pickle.load(pickle_in)
pickle_in = open("action_mapping_inet.pickle","rb") ;action_mapping=pickle.load(pickle_in)
pickle_in = open("all_imgs_inet.pickle","rb") ;all_imgs=pickle.load(pickle_in)



if 'bg' not in classes_count:
    classes_count['bg'] = 0
    class_mapping['bg'] = len(class_mapping)

C.class_mapping = class_mapping

inv_map = {v: k for k, v in class_mapping.items()}

print('Training images per class:')
pprint.pprint(classes_count)
print('Num classes (including bg) = {}'.format(len(classes_count)))

config_output_filename = options.config_filename

with open(config_output_filename, 'wb') as config_f:
    pickle.dump(C, config_f)
    print('Config has been written to {}, and can be loaded when testing to ensure correct results'.format(config_output_filename))



random.shuffle(all_imgs)

num_imgs = len(all_imgs)

train_imgs = [s for s in all_imgs if s['imageset'] == 'train']
val_imgs = [s for s in all_imgs if s['imageset'] == 'val']
test_imgs = [s for s in all_imgs if s['imageset'] == 'test']

'''
pickle_out = open("data_gen_train_inet.pickle","wb") ;pickle.dump(train_imgs, pickle_out) ;pickle_out.close();
pickle_out = open("data_gen_val_inet.pickle","wb") ;pickle.dump(val_imgs, pickle_out) ;pickle_out.close();
pickle_out = open("data_gen_test_inet.pickle","wb") ;pickle.dump(test_imgs, pickle_out) ;pickle_out.close();

pickle_in = open("data_gen_train.pickle","rb");train_imgs = pickle.load(pickle_in)
pickle_in = open("data_gen_val.pickle","rb");val_imgs = pickle.load(pickle_in)
pickle_in = open("data_gen_test.pickle","rb");test_imgs = pickle.load(pickle_in)
'''

print('Num train samples {}'.format(len(train_imgs)))
print('Num val samples {}'.format(len(val_imgs)))
print('Num test samples {}'.format(len(test_imgs)))

data_gen_train = data_generators.get_anchor_gt(train_imgs, classes_count, C, nn.get_img_output_length, K.image_dim_ordering(), mode='train')
data_gen_val = data_generators.get_anchor_gt(val_imgs, classes_count, C, nn.get_img_output_length, K.image_dim_ordering(), mode='val')
data_gen_test = data_generators.get_anchor_gt(test_imgs, classes_count, C, nn.get_img_output_length, K.image_dim_ordering(), mode='val')


if K.image_dim_ordering() == 'th':
    input_shape_img = (3, None, None)
else:
    input_shape_img = (None, None, 3)

img_input = Input(shape=input_shape_img)
roi_input = Input(shape=(None, 4))

shared_layers = nn.nn_base(img_input, trainable=True)

# define the RPN, built on the base layers
num_anchors = len(C.anchor_box_scales) * len(C.anchor_box_ratios)
rpn = nn.rpn(shared_layers, num_anchors)

classifier = nn.classifier(shared_layers, roi_input, C.num_rois, nb_classes=len(classes_count), trainable=True)
classifier_branch2 = nn.classifier_branch2(shared_layers, roi_input, num_rois_h, nb_classes=len(actions_count), trainable=True)#harmeet. What is nb_classes ?

model_rpn = Model(img_input, rpn[:2])
model_classifier = Model([img_input, roi_input], classifier)
model_classifier_branch2 = Model([img_input, roi_input], classifier_branch2)
#plot_model(model_classifier_branch2,"branch2.png",show_shapes=True,show_layer_names=True)
#plot_model(model_classifier,"original.png",show_shapes=True,show_layer_names=True)
# this is a model that holds both the RPN and the classifier, used to load/save weights for the models
model_all = Model([img_input, roi_input], rpn[:2] + classifier + classifier_branch2)

try:
    # load_weights by name
    # some keras application model does not containing name
    # for this kinds of model, we need to re-construct model with naming
    print('loading weights from {}'.format(C.base_net_weights))
    model_rpn.load_weights(C.base_net_weights, by_name=True)
    model_classifier.load_weights(C.base_net_weights, by_name=True)
except:
    print('Could not load pretrained model weights. Weights can be found in the keras application folder \
        https://github.com/fchollet/keras/tree/master/keras/applications')

optimizer = Adam(lr=1e-5)
optimizer_classifier = Adam(lr=1e-5)
model_rpn.compile(optimizer=optimizer, loss=[losses.rpn_loss_cls(num_anchors), losses.rpn_loss_regr(num_anchors)])
model_classifier.compile(optimizer=optimizer_classifier, loss=[losses.class_loss_cls, losses.class_loss_regr(len(classes_count)-1)], metrics={'dense_class_{}'.format(len(classes_count)): 'accuracy'})
model_classifier_branch2.compile(optimizer=optimizer_classifier, loss=[losses.class_loss_cls, losses.class_loss_regr(len(actions_count)-1)], metrics={'dense_class_{}'.format(len(actions_count)): 'accuracy'})



model_all.compile(optimizer='sgd', loss='mae')

log_path = './logs'
if not os.path.isdir(log_path):
    os.mkdir(log_path)

callback = TensorBoard(log_path)
callback.set_model(model_all)

epoch_length = 1000
num_epochs = int(options.num_epochs)
iter_num = 0
train_step = 0

losses = np.zeros((epoch_length, 8))
rpn_accuracy_rpn_monitor = []
rpn_accuracy_for_epoch = []
start_time = time.time()

best_loss = np.Inf

class_mapping_inv = {v: k for k, v in class_mapping.items()}

print('Starting training')

# vis = True

for epoch_num in range(num_epochs):

    progbar = generic_utils.Progbar(epoch_length)
    print('Epoch {}/{}'.format(epoch_num + 1, num_epochs))

    while True:
        # try:

        if len(rpn_accuracy_rpn_monitor) == epoch_length and C.verbose:
            mean_overlapping_bboxes = float(sum(rpn_accuracy_rpn_monitor))/len(rpn_accuracy_rpn_monitor)
            rpn_accuracy_rpn_monitor = []
            print('Average number of overlapping bounding boxes from RPN = {} for {} previous iterations'.format(mean_overlapping_bboxes, epoch_length))
            if mean_overlapping_bboxes == 0:
                print('RPN is not producing bounding boxes that overlap the ground truth boxes. Check RPN settings or keep training.')

        X, Y, img_data = next(data_gen_train)

        loss_rpn = model_rpn.train_on_batch(X, Y)
        write_log(callback, ['rpn_cls_loss', 'rpn_reg_loss'], loss_rpn, train_step)

        P_rpn = model_rpn.predict_on_batch(X)

        R = roi_helpers.rpn_to_roi(P_rpn[0], P_rpn[1], C, K.image_dim_ordering(), use_regr=True, overlap_thresh=0.7, max_boxes=300)

        X2, Y1, Y2, IouS = roi_helpers.calc_iou(R, img_data, C, class_mapping)
        X2_h, Y1_h, Y2_boh, IouS_h = roi_helpers.calc_iou_human(R, img_data, C, action_mapping, num_rois_h)

        if X2 is None or X2_h is None or X2_h.shape[1] < num_rois_h :
            rpn_accuracy_rpn_monitor.append(0)
            rpn_accuracy_for_epoch.append(0)
            continue

        # sampling positive/negative samples
        neg_samples = np.where(Y1[0, :, -1] == 1)
        pos_samples = np.where(Y1[0, :, -1] == 0)
        pos_samples_h = np.where(Y1_h[0, :, -1] != 3) # harmeet this is a bad hack

        if len(neg_samples) > 0:
            neg_samples = neg_samples[0]
        else:
            neg_samples = []

        if len(pos_samples) > 0:
            pos_samples = pos_samples[0]
        else:
            pos_samples = []

        if( len(pos_samples_h)) > 0:
            pos_samples_h = pos_samples_h[0]



        rpn_accuracy_rpn_monitor.append(len(pos_samples))
        rpn_accuracy_for_epoch.append((len(pos_samples)))

        rpn_accuracy_rpn_monitor.append(num_rois_h)
        rpn_accuracy_for_epoch.append((num_rois_h))

        if C.num_rois > 1:
            if len(pos_samples) < C.num_rois//4:
                selected_pos_samples = pos_samples.tolist()
            else:
                selected_pos_samples = np.random.choice(pos_samples, C.num_rois//4, replace=False).tolist()
            try:
                selected_neg_samples = np.random.choice(neg_samples, C.num_rois - len(selected_pos_samples), replace=False).tolist()
            except:
                selected_neg_samples = np.random.choice(neg_samples, C.num_rois - len(selected_pos_samples), replace=True).tolist()

            sel_samples = selected_pos_samples + selected_neg_samples
        else:
            # in the extreme case where num_rois = 1, we pick a random pos or neg sample
            selected_pos_samples = pos_samples.tolist()
            selected_neg_samples = neg_samples.tolist()
            if np.random.randint(0, 2):
                sel_samples = random.choice(neg_samples)
            else:
                sel_samples = random.choice(pos_samples)


        sel_samples_h = pos_samples_h.tolist() #+ selected_neg_samples_h

        loss_class = model_classifier.train_on_batch([X, X2[:, sel_samples, :]], [Y1[:, sel_samples, :], Y2[:, sel_samples, :]])
        loss_class_branch2 = model_classifier_branch2.train_on_batch([X, X2_h[:, sel_samples_h, :]],[Y1_h[:, sel_samples_h, :], Y2_boh[:, sel_samples_h, :]])

        write_log(callback, ['detection_cls_loss', 'detection_reg_loss', 'detection_acc'], loss_class, train_step)
        train_step += 1

        losses[iter_num, 0] = loss_rpn[1]
        losses[iter_num, 1] = loss_rpn[2]

        losses[iter_num, 2] = loss_class[1]
        losses[iter_num, 3] = loss_class[2]
        losses[iter_num, 4] = loss_class[3]

        losses[iter_num, 5] = loss_class[1]
        losses[iter_num, 6] = loss_class[2]
        losses[iter_num, 7] = loss_class[3]

        iter_num += 1


        progbar.update(iter_num,
                       [
                            ('rpn_cls', np.mean(losses[:iter_num, 0])), ('rpn_regr', np.mean(losses[:iter_num, 1])),
                            ('detector_cls', np.mean(losses[:iter_num, 2])),
                            ('detector_regr', np.mean(losses[:iter_num, 3])),
                           ('detector_cls2', np.mean(losses[:iter_num, 5])),
                           ('detector_regr2', np.mean(losses[:iter_num, 6]))
                        ])


        if iter_num == epoch_length:
            loss_rpn_cls = np.mean(losses[:, 0])
            loss_rpn_regr = np.mean(losses[:, 1])
            loss_class_cls = np.mean(losses[:, 2])
            loss_class_regr = np.mean(losses[:, 3])
            class_acc = np.mean(losses[:, 4])

            loss_class_cls_branch2 = np.mean(losses[:, 5])
            loss_class_regr_branch2 = np.mean(losses[:, 6])
            class_acc_branch2 = np.mean(losses[:, 7])

            mean_overlapping_bboxes = float(sum(rpn_accuracy_for_epoch)) / len(rpn_accuracy_for_epoch)
            rpn_accuracy_for_epoch = []

            if C.verbose:
                print('Mean number of bounding boxes from RPN overlapping ground truth boxes: {}'.format(mean_overlapping_bboxes))
                print('Classifier accuracy for bounding boxes from RPN: {}'.format(class_acc))
                print('Loss RPN classifier: {}'.format(loss_rpn_cls))
                print('Loss RPN regression: {}'.format(loss_rpn_regr))
                print('Loss Detector classifier: {}'.format(loss_class_cls))
                print('Loss Detector regression: {}'.format(loss_class_regr))
                print('Elapsed time: {}'.format(time.time() - start_time))

            curr_loss = loss_rpn_cls + loss_rpn_regr + loss_class_cls + loss_class_regr+ (2*loss_class_cls_branch2) + loss_class_regr_branch2

            iter_num = 0
            start_time = time.time()

            write_log(callback,
                      ['Elapsed_time', 'mean_overlapping_bboxes', 'mean_rpn_cls_loss', 'mean_rpn_reg_loss',
                       'mean_detection_cls_loss', 'mean_detection_reg_loss', 'mean_detection_acc', 'total_loss'],
                      [time.time() - start_time, mean_overlapping_bboxes, loss_rpn_cls, loss_rpn_regr,
                       loss_class_cls, loss_class_regr, class_acc, curr_loss],
                      epoch_num)

            if curr_loss < best_loss:
                if C.verbose:
                    print('Total loss decreased from {} to {}, saving weights'.format(best_loss,curr_loss))
                best_loss = curr_loss
                model_all.save_weights(C.model_path)

            break
print('Training complete, exiting.')
