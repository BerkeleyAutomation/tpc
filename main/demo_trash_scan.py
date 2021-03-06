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

from il_ros_hsr.core.grasp_planner import GraspPlanner
from il_ros_hsr.core.crane_gripper import Crane_Gripper

from il_ros_hsr.p_pi.bed_making.com import Bed_COM as COM
import sys



from il_ros_hsr.p_pi.tpc.gripper import Lego_Gripper
from tpc.perception.cluster_registration import run_connected_components, visualize
from tpc.perception.singulation import Singulation
from tpc.perception.crop import crop_img
from perception import ColorImage, BinaryImage
from il_ros_hsr.p_pi.bed_making.table_top import TableTop

import il_ros_hsr.p_pi.bed_making.config_bed as cfg


from il_ros_hsr.core.rgbd_to_map import RGBD2Map

SINGULATE = True

DIST_TOL = 5 #number of pixels apart to be singulated

COLOR_TOL = 40 #background range for thresholding the image

SIZE_TOL = 300 #number of pixels necssary for a cluster


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

        self.gripper = Crane_Gripper(self.gp,self.cam,self.com.Options,self.robot.get('gripper'))

        print "after thread"

       
    def scan_area(self):

        self.tt.move_to_pose(self.omni_base,'right_down')
      
    
        self.tt.move_to_pose(self.omni_base,'right_up')

        self.tt.move_to_pose(self.omni_base,'top_mid')

        while True:
            self.tt.move_to_pose(self.omni_base,'top_left_far')
            self.tt.move_to_pose(self.omni_base,'top_mid_far')
            self.tt.move_to_pose(self.omni_base,'top_mid')




    def find_mean_depth(self,d_img):
        '''
        Evaluates the current policy and then executes the motion 
        specified in the the common class
        '''

        indx = np.nonzero(d_img)

        mean = np.mean(d_img[indx])

        return


    def execute_grasp(self,grasp_name):
        self.gripper.open_gripper()

        self.whole_body.end_effector_frame = 'hand_palm_link'
        
        self.whole_body.move_end_effector_pose(geometry.pose(),grasp_name)

        self.gripper.close_gripper()
        self.whole_body.move_end_effector_pose(geometry.pose(z=-0.1),grasp_name)        
        
        self.whole_body.move_end_effector_pose(geometry.pose(z=-0.1),'head_down')
        
    
        self.gripper.open_gripper()


    def compute_grasp(self, c_m, direction, d_img):
        #convert from image to world (flip x)
        dx = direction[1]
        dy = direction[0]
        dx *= -1
        #standardize to 1st/2nd quadrants
        if dy < 0:
            dx *= -1
            dy *= -1
        rot = np.arctan2(dy, dx)
        #convert to robot view (counterclockwise)
        rot = 3.14 - rot
        # IPython.embed()
        # if direction: 
        #     rot = 0.0
        # else: 
        #     rot = 1.57

        x = int(c_m[1])
        y = int(c_m[0])

        z_box = d_img[y-20:y+20,x-20:x+20]

        z = self.gp.find_mean_depth(z_box)

        return [x,y,z],rot

        
    def go_to_point(self, point, rot, c_img, d_img):
        y, x = point
        z_box = d_img[y-20:y+20, x-20:x+20]
        z = self.gp.find_mean_depth(z_box)
        print "singulation pose:", x,y,z
        pose_name = self.gripper.get_grasp_pose(x,y,z,rot,c_img=c_img)
        raw_input("Click enter to move to " + pose_name)
        self.whole_body.move_end_effector_pose(geometry.pose(), pose_name)

    
    def position_head(self):

        self.tt.move_to_pose(self.omni_base,'lower_start')
        self.whole_body.move_to_joint_positions({'head_tilt_joint':-0.8})

        




if __name__ == "__main__":
    if len(sys.argv) > 1:
        DEBUG = True
    else:
        DEBUG = False
    
    cp = BedMaker()
    cp.scan_area()