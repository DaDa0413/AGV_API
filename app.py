#!/usr/bin/python
from __future__ import print_function
import sys
from GUI import Ui_MainWindow
from PyQt4.QtCore import *
from PyQt4.QtGui import *

import cv2
from recognize_face_imgs import recognize

import webbrowser
import pyrealsense2 as rs
import numpy as np

import roslib 
import rospy
import actionlib
import geometry_msgs
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal
from geometry_msgs.msg import Twist
import tf.transformations
import time
# from rotate_agv import rotate_agv 

class ros_node(QThread):

    def __init__(self, x, y, heading, parent=None):
        QThread.__init__(self, parent=parent)

        print('[NODE] Starting ROS node...')
        rospy.init_node('app_client')
        
        print('[NODE] x=' + str(x) + ' y=' + str(y) + ' h=' + str(heading))
        self.x = x
        self.y = y
        self.heading = heading
        

    def run(self):
        # Creates the SimpleActionClient
        self.move_base_client = actionlib.SimpleActionClient('/move_base', MoveBaseAction)

        # Waits until the action server has started up and started
        # listening for goals.
        print ('[NODE] Waiting for server...')
        self.move_base_client.wait_for_server()

        # Creates a goal to send to the action server.
        pose = geometry_msgs.msg.Pose()
        pose.position.x = self.x
        pose.position.y = self.y
        pose.position.z = 0.0
        if (self.heading != None) :
            q = tf.transformations.quaternion_from_euler(0, 0, self.heading)
            pose.orientation = geometry_msgs.msg.Quaternion(*q)
        goal = MoveBaseGoal()
        goal.target_pose.pose = pose
        goal.target_pose.header.frame_id = 'map'
        goal.target_pose.header.stamp = rospy.Time.now()


        # Sends the goal to the action server.
        print('[NODE] Sending goal to action server: %s' % goal)
        self.move_base_client.send_goal(goal)

        canceltime = None

        if canceltime != None:
            print('[NODE] Letting action server work for 3 seconds but then cancelling...')
            time.sleep(canceltime)
            print('[NODE] Cancelling current goal...')
            self.move_base_client.cancel_goal()
        else:
            # Waits for the server to finish performing the action.
            print('[NODE] Waiting for result...')
            self.move_base_client.wait_for_result()

        print('[NODE] Result received. Action state is %s' % self.move_base_client.get_state())
        print('[NODE] Goal status message is %s' % self.move_base_client.get_goal_status_text())

        #return move_base_client.get_result() 

    def cancel(self):
        print('[NODE] Cancelling Goal ...')
        self.move_base_client.cancel_goal()


class rs_camera(QThread):

    refresh = pyqtSignal(np.ndarray)
    
    def __init__(self, parent=None):
        QThread.__init__(self, parent=parent)
        
        # Camera settings
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 30)
        self.pipeline.start(self.config)
        print('[INFO] Camera started')
        self.running = True

    def run(self):
        while self.running:
            frames = self.pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue        
            color_image = np.asanyarray(color_frame.get_data())
            self.refresh.emit(color_image)

    def stop(self):
        self.running = False
        print('[INFO] Terminating Camera')
        self.pipeline.stop()

class rotate(QThread):
    rotate_done = pyqtSignal()

    def __init__(self, target, parent=None):
        QThread.__init__(self, parent=parent)
        self.target = target
        rospy.init_node('rotate_agv')

        self.pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)

        # Rotate message
        self.rot = Twist()
        self.rotate_rate = rospy.Rate(3)

    def run(self):

        self.rot.angular.z = 0.5

        start = time.time()
        while time.time() - start < 2:
            self.pub.publish(self.rot)
            self.rotate_rate.sleep()

        self.rotate_done.emit()

    def stop(self):
        pass



class web_camera(QThread):

    refresh = pyqtSignal(np.ndarray)

    def __init__(self, parent=None):
        QThread.__init__(self, parent=parent)
        self.cap = cv2.VideoCapture(0)
        print('[INFO] Camera started')
        self.running = True
    
    def run(self):
        while self.running:
            ret, frame = self.cap.read()
            self.image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.refresh.emit(self.image)
    
    def stop(self):
        self.running = False
        print('[INFO] Terminating Camera')
        self.cap.release()

class MainWindow(QMainWindow, Ui_MainWindow):
    
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        self.onBindingUI()
        self.image = []
        self.set_authority(False)
        self.th = web_camera(self)
        self.th.start()
        self.camera_running = True
        self.th2 = None
        self.r_th = rotate(self, self)
        self.r_th.rotate_done.connect(self.on_btn_verify_click)

    def drawPicture(self, img, cache=True):
        if cache:
            self.image = img
        height, width, bytesPerComponent = img.shape
        bytesPerLine = 3 * width
        QImg = QImage(img.data, width, height, bytesPerLine, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(QImg)
        scaledPix = pixmap.scaled(self.viewer.size(), Qt.KeepAspectRatio)
        self.viewer.setPixmap(scaledPix)

    def onBindingUI(self):
        self.btn_takePhoto.clicked.connect(self.on_btn_takePhoto_click)
        self.btn_verify.clicked.connect(self.on_btn_verify_click)
        self.btn_openLink.clicked.connect(self.on_btn_openLink_click)
        self.btn_clear.clicked.connect(self.on_btn_clear_click)
        self.btn_ok.clicked.connect(self.on_btn_ok_click)
        self.btn_quit.clicked.connect(self.on_btn_quit_click)
        self.btn_home.clicked.connect(self.on_btn_home_click)
        self.btn_point.clicked.connect(self.on_btn_point_click)
        self.btn_cancel.clicked.connect(self.on_btn_cancel_click)

    def on_btn_takePhoto_click(self):
        print('[INFO] Take Photo button pressed')
        self.th.refresh.connect(lambda p:self.drawPicture(p))
        # self.image = cv2.imread("examples/test9.png")
        # cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB, self.image)
        # self.drawPicture(self.image.copy())
        
    def set_authority(self, authorized):
        if authorized:
            self.label_status.setText("Authorized")
            self.label_status.setStyleSheet("QLabel{color:rgb(0,255,0)}")
            self.btn_openLink.setEnabled(True)
        else:
            self.label_status.setText("Unauthorized")
            self.label_status.setStyleSheet("QLabel{color:rgb(255,0,0)}")
            self.btn_openLink.setEnabled(False)

    def verify(self, image):
        
        if len(image) == 0:
            print('[ERRO] No image found!')
            self.set_authority(False)
            return

        image, names = recognize(image)
        
        if len(names) == 0:
            print('[WARN] No person in the image')
            self.set_authority(False)
        elif len(names) > 1:
            print('[WARN] Multiple people in the image')
            self.set_authority(False)
        else:
            text = str(self.comboBox.currentText())
            if names[0] == 'Unknown':
                print('[WARN] Unknown person')
                self.set_authority(False)
                self.drawPicture(image.copy(),cache=False)
            elif names[0] == text:
                print('[INFO] Authorized User: '+text)
                self.set_authority(True)
                self.drawPicture(image.copy(),cache=False)
            else:
                print('[WARN] Unauthorized User')
                self.set_authority(False)
    
    
    def on_btn_verify_click(self):
        print('[INFO] verify button pressed')
        self.verify(self.image.copy())
        
    

    def on_btn_openLink_click(self):
        print('[INFO] Open Link button pressed')
        self.th.stop()
        self.camera_running = False
        self.btn_takePhoto.setEnabled(False)
        webbrowser.open("https://appr.tc/r/19980202")
	

    def on_btn_clear_click(self):
        self.viewer.clear()
        self.image = []

    def on_btn_ok_click(self):
        self.th.refresh.disconnect()

    def on_btn_quit_click(self):
        print('[INFO] Quit Application')
        if self.camera_running:
            self.th.stop()
        self.close()

    def on_btn_home_click(self):
        # self.th2 = ros_node(6.25,0.463,0,self)
        # self.th2.start()
        self.r_th.start()


        # while not )rospy.is_shutdown()
    
    def on_btn_point_click(self):
        x = float(self.pos_x.text())
        y = float(self.pos_y.text())
        h = float(self.pos_h.text())
        
        self.th2 = ros_node(x,y,h,self)
        self.th2.start()

    def on_btn_cancel_click(self):
        if self.th2:
            self.th2.cancel()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
