import cv2
import IPython
import time
import numpy as np
import sys

from tpc.manipulation.robot_actions import Robot_Actions
# from tpc.data_logger import DataLogger
import tpc.config.config_tpc as cfg

import thread
import tf
import rospy
import os
import json
import shutil

if cfg.robot_name == "hsr":
    from core.hsr_robot_interface import Robot_Interface
elif cfg.robot_name == "fetch":
    from core.fetch_robot_interface import Robot_Interface 
elif cfg.robot_name is None:
    from tpc.offline.robot_interface import Robot_Interface

from spawn_object_script import *
from gazebo_msgs.srv import DeleteModel, SpawnModel, GetWorldProperties, SetPhysicsProperties
import gazebo_msgs.msg
from std_msgs.msg import Float64

# from segmentation import *
from segmentation_rgb import *

def depth_scaled_to_255(img):
	img = 255.0/np.max(img)*img
	img = np.array(img,dtype=np.uint8)
	
	img[:,:] = cv2.equalizeHist(img[:,:])
	# cv2.imshow('debug.png',img)
	return img



class DataCollection():

	def __init__(self):
		"""
		Class that runs decluttering task

		"""
		self.robot = Robot_Interface()
		self.ra = Robot_Actions(self.robot)

		self.dm, self.sm, self.om = setup_delete_spawn_service()

		print "Finished init"

		clean_floor(self.dm, self.om)

		time.sleep(2)


	def collect(self, dataset_size=1000):

		# IMDIR = 'sim_data/test/'
		# time_sum = []
		#IMDIR = 'sim_data/test_floorplan/'
		IMDIR="sim_data/dataset_08_22_2018_2/"

		if not os.path.exists(IMDIR):
			os.makedirs(IMDIR)
		if not os.path.exists(IMDIR+"bb_labels"):
			os.makedirs(IMDIR+"bb_labels")
		if not os.path.exists(IMDIR+"bbs"):
			os.makedirs(IMDIR+"bbs")
		if not os.path.exists(IMDIR+"gt"):
			os.makedirs(IMDIR+"gt")
		if not os.path.exists(IMDIR+"image_depth"):
			os.makedirs(IMDIR+"image_depth")
		if not os.path.exists(IMDIR+"image_labels"):
			os.makedirs(IMDIR+"image_labels")
		if not os.path.exists(IMDIR+"image_rgb"):
			os.makedirs(IMDIR+"image_rgb")
		if not os.path.exists(IMDIR+"json_labels"):
			os.makedirs(IMDIR+"json_labels")

		start = len([x for x in os.listdir(IMDIR+"bbs") if 'png' in x])

		i = 0
		total = 0
		reject1 = 0
		reject2 = 0
		reject3 = 0

		while i < dataset_size:
			if total%10 == 0:
				self.dm, self.sm, self.om = setup_delete_spawn_service()

				print "Reinitialized spawning service"

				clean_floor(self.dm, self.om)

				self.ra.go_to_start_position()
				self.ra.go_to_start_pose()

			print(i, total, reject1, reject2, reject3)

			total += 1

			print(i+start)
			
			# if not os.path.exists(IMDIR+str(i+start)):
			# 	os.makedirs(IMDIR+str(i+start))

			time.sleep(0.1)


			# time.sleep(0.1)

			n = np.random.randint(5, 15)
			# n=1

			spawn_from_uniform(n, self.sm)
			# time_sum.append(np.mean(time_array, axis=0).tolist())
			# print(np.mean(time_array, axis=0))
			
			labels = get_object_list(self.om)

			img_lst = []

			for j in range(len(labels)):
				if len(get_object_list(self.om)) + j != len(labels):
					delete_correct = False
				c_img, d_img = self.robot.get_img_data()
				delete_object(labels[len(labels) - 1 - j], self.dm)
				img_lst.insert(0, c_img)
				# time.sleep(0.1)
				# cv2.imwrite(IMDIR+str(i+start)+'/rgb_{}.png'.format(str(len(labels) -1- j)), c_img)
				# cv2.imwrite(IMDIR+str(i+start)+'/depth_{}.png'.format(str(len(labels) -1- j)), depth_scaled_to_255(np.array((d_img * 1000).astype(np.int16))))
				if j == 0:
					cv2.imwrite(IMDIR+'image_rgb/rgb_{}.png'.format(str(i+start)), c_img)
					import ipdb; ipdb.set_trace()
					cv2.imwrite(IMDIR+'image_depth/depth_{}.png'.format(str(i+start)), depth_scaled_to_255(np.array((d_img).astype(np.int16))))
					all_items = c_img

			clean_floor(self.dm, self.om)
			time.sleep(0.1)

			c_img, d_img = self.robot.get_img_data()
			img_lst.append(c_img)

			# cv2.imwrite(IMDIR+str(i+start)+'/rgb_background.png', c_img)
			# cv2.imwrite(IMDIR+str(i+start)+'/depth_background.png', depth_scaled_to_255(np.array((d_img * 1000).astype(np.int16))))
			# print(np.array((d_img * 1000).astype(np.int16)).dtype)

			
			# with open(IMDIR+str(i+start)+"/labels.json", 'w') as f:
			# 	json.dump(labels, f)

			mask_lst, noshift, nooverlap = find_item_masks(img_lst, labels)

			if len(get_object_list(self.om)) > 0:
				sys.exit()
			
			if not noshift:
				os.remove(IMDIR+'image_rgb/rgb_{}.png'.format(str(i+start)))
				os.remove(IMDIR+'image_depth/depth_{}.png'.format(str(i+start)))
				# print("shifting")
				reject1 += 1
				continue
			if not nooverlap:
				os.remove(IMDIR+'image_rgb/rgb_{}.png'.format(str(i+start)))
				os.remove(IMDIR+'image_depth/depth_{}.png'.format(str(i+start)))
				# print("shifting")
				reject2 += 1
				continue
			compare, diff, seg_image, bb_image, valid_label = draw_masks(mask_lst, all_items, labels, img_lst)



			if diff > 640*480/300:
				os.remove(IMDIR+'image_rgb/rgb_{}.png'.format(str(i+start)))
				os.remove(IMDIR+'image_depth/depth_{}.png'.format(str(i+start)))
				reject3 += 1
				# print(diff)
			else:
				cv2.imwrite(IMDIR+'gt/compare_{}.png'.format(str(i+start)), compare)
				cv2.imwrite(IMDIR+'image_labels/seg_{}.png'.format(str(i+start)), seg_image)
				cv2.imwrite(IMDIR+'bbs/bb_{}.png'.format(str(i+start)), bb_image)
				create_segment_label(IMDIR, str(i+start), labels, mask_lst)
				# print(i+start, noshift)
				i+=1

			# shutil.rmtree(IMDIR+str(i+start))
			time.sleep(0.1)
			# print(i, total, reject1, reject2)

			

			
			# i += 1

			

			# time.sleep(3)
			# self.ra.go_to_start_position()
			# self.ra.go_to_start_pose()
			
			# time.sleep(2)
		# with open(IMDIR+"/time.json", 'w') as f:
		# 	json.dump(time_sum, f)


if __name__ == "__main__":
	DataCollection().collect(dataset_size=50)




