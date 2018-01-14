from hsrb_interface import geometry
import hsrb_interface
from geometry_msgs.msg import PoseStamped, Point, WrenchStamped
import geometry_msgs
import controller_manager_msgs.srv
import cv2
from cv_bridge import CvBridge, CvBridgeError
import IPython
from numpy.random import normal
import time
#import listener
import thread

from geometry_msgs.msg import Twist
from sensor_msgs.msg import Joy

from il_ros_hsr.core.sensors import  RGBD, Gripper_Torque, Joint_Positions
from il_ros_hsr.core.joystick import  JoyStick

import matplotlib.pyplot as plt

import numpy as np
import numpy.linalg as LA
from tf import TransformListener
import tf
import rospy

from il_ros_hsr.core.crane_gripper import Crane_Gripper
from il_ros_hsr.core.grasp_planner import GraspPlanner

from il_ros_hsr.p_pi.bed_making.com import Bed_COM as COM
import sys


from il_ros_hsr.p_pi.tpc.gripper import Lego_Gripper
from tpc.perception.cluster_registration import run_connected_components, display_grasps, has_multiple_objects, grasps_within_pile, view_hsv, get_hsv_hist
from tpc.perception.singulation import find_singulation, display_singulation
from tpc.perception.crop import crop_img
from tpc.manipulation.primitives import GraspManipulator
from perception import ColorImage, BinaryImage
from il_ros_hsr.p_pi.bed_making.table_top import TableTop

import tpc.config.config_tpc as cfg

from il_ros_hsr.core.rgbd_to_map import RGBD2Map

class BedMaker():

    def __init__(self):
        '''
        Initialization class for a Policy

        Parameters
        ----------
        yumi : An instianted yumi robot
        com : The common class for the robot
        cam : An open bincam class

        debug : bool

            A bool to indicate whether or not to display a training set point for
            debuging.

        '''

        self.robot = hsrb_interface.Robot()
        self.rgbd_map = RGBD2Map()

        self.omni_base = self.robot.get('omni_base')
        self.whole_body = self.robot.get('whole_body')


        self.side = 'BOTTOM'

        self.cam = RGBD()
        self.com = COM()

        if not DEBUG:
            self.com.go_to_initial_state(self.whole_body)

            self.tt = TableTop()
            self.tt.find_table(self.robot)

        self.grasp_count = 0

        self.br = tf.TransformBroadcaster()
        self.tl = TransformListener()

        self.gp = GraspPlanner()
        self.gripper = Crane_Gripper(self.gp, self.cam, self.com.Options, self.robot.get('gripper'))

        self.gm = GraspManipulator(self.gp, self.gripper, self.whole_body, self.omni_base, self.tt)

        print "after thread"

    def find_mean_depth(self,d_img):
        '''
        Evaluates the current policy and then executes the motion
        specified in the the common class
        '''

        indx = np.nonzero(d_img)

        mean = np.mean(d_img[indx])

        return

    def lego_demo(self):

        self.rollout_data = []
        self.get_new_grasp = True

        if not DEBUG:
            self.gm.position_head()
        b = time.time()
        while True:
            time.sleep(1) #making sure the robot is finished moving

            a = time.time()
            c_img = self.cam.read_color_data()
            d_img = self.cam.read_depth_data()
            cv2.imwrite("debug_imgs/c_img.png", c_img)
            print "time to get images", time.time() - a
            print "\n new iteration"
            if(not c_img == None and not d_img == None):
                main_mask = crop_img(c_img)
                col_img = ColorImage(c_img)
                workspace_img = col_img.mask_binary(main_mask)

                a = time.time()
                center_masses, directions, masks = run_connected_components(workspace_img,
                    cfg.DIST_TOL, cfg.COLOR_TOL, cfg.SIZE_TOL, viz=False)
                print "Time to find masses:", time.time() - a
                print "num masses", len(center_masses)
                if len(center_masses) == 0:
                    print("cleared workspace")
                    break

                # for i, m in enumerate(masks):
                #     cv2.imwrite("debug_imgs/" + str(i) + ".png", m)
                # nums = [len(k.nonzero_pixels()) for k in masks]

                has_multiple = [has_multiple_objects(col_img.mask_binary(m), alg="hsv") for m in masks]
                print "has multiple objects?:", has_multiple

                #TOFIX- visualization messed up somewhere- modified workspace_img with false grasps

                grasps = []
                graspmasks = []
                viz_info = []
                for i in range(len(center_masses)):
                    if not has_multiple[i]:
                        cm = center_masses[i]
                        di = directions[i]
                        viz_info.append([cm, di])
                        pose,rot = self.gm.compute_grasp(cm, di,d_img)
                        graspmasks.append(masks[i])
                        grasps.append(self.gripper.get_grasp_pose(pose[0],pose[1],pose[2],rot,c_img=workspace_img.data))
                    else:
                        new_cms, new_dirs = grasps_within_pile(col_img.mask_binary(masks[i]))
                        for j in range(len(new_cms)):
                            new_cm = new_cms[j]
                            new_di = new_dirs[j]
                            viz_info.append([new_cm, new_di])
                            pose,rot = self.gm.compute_grasp(new_cm,new_di,d_img)
                            graspmasks.append(masks[i])
                            grasps.append(self.gripper.get_grasp_pose(pose[0],pose[1],pose[2],rot,c_img=workspace_img.data))

                if len(grasps) > 0:
                    print "running grasps"
                    display_grasps(workspace_img, [v[0] for v in viz_info], [v[1] for v in viz_info],
                    name = "grasps")
                    IPython.embed()
                    for i, grasp in enumerate(grasps):
                        # raw_input("Click enter to execute grasp:" + grasp)
                        print "grasping", grasp
                        curr_mask = graspmasks[i]
                        curr_col = col_img.mask_binary(curr_mask)
                        counts, _ = get_hsv_hist(curr_col, num_bins=3)
                        color = max(counts, key=lambda k:counts[k])
                        self.gm.execute_grasp(grasp, color)
                else:
                    print("singulating")
                    a = time.time()
                    #singulate smallest pile
                    masks.sort(key=lambda m:len(m.nonzero_pixels()))
                    curr_pile = masks[0]
                    other_piles = masks[1:]
                    start, end, rot, free_pix, mid = find_singulation(col_img, main_mask, curr_pile,
                        other_piles, alg="border")
                    print "Time to find Singulate:", time.time() - a
                    display_singulation(start, end, mid, workspace_img, free_pix, 
                        name = "singulate")
                    IPython.embed()
                    self.gm.singulate(start, end, mid, rot, c_img, d_img, expand=True)
                # self.tt.move_to_pose(self.omni_base,'lower_start')
                print "Current Time:", time.time() - b

                self.whole_body.move_to_go()
                self.gm.position_head()
                IPython.embed()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        DEBUG = True
    else:
        DEBUG = False

    cp = BedMaker()

    # cp.bed_make()
    cp.lego_demo()
