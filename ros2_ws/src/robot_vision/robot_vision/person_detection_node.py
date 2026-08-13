import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2D
import cv2
from cv_bridge import CvBridge
import numpy as np

# In an actual deployment, YOLOv11 and InsightFace libraries would be imported:
# from ultralytics import YOLO
# import insightface

class PersonDetectionNode(Node):
    def __init__(self):
        super().__init__('person_detection_node')
        self.subscription = self.create_subscription(
            Image,
            '/camera/image_raw',
            self.image_callback,
            10
        )
        self.publisher_ = self.create_publisher(Detection2D, '/vision/host_identified', 10)
        self.bridge = CvBridge()
        self.get_logger().info("YOLOv11 and InsightFace Host Identification Node Initialized.")
        
        # Load Host Face model parameters (Simulated for package template structure)
        self.host_verified = False
        self.host_name = "Priyam_Patel"

    def image_callback(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        h, w, _ = frame.shape
        
        # --- YOLOv11 Inference & InsightFace recognition (Simulated pipeline) ---
        # 1. Run YOLOv11 person detection
        # 2. Extract bounding boxes for people
        # 3. Align face crop and run InsightFace extractor
        # 4. Compare current face embedding against host database
        
        # For simulation, we assume a verified host is present in the center of the frame
        host_detected = True
        
        if host_detected:
            # Generate simulated host bounding box in center
            bbox_x = float(w // 2)
            bbox_y = float(h // 2)
            bbox_w = 120.0
            bbox_h = 240.0
            
            # Pack ROS 2 Detection2D message
            det_msg = Detection2D()
            det_msg.header = msg.header
            det_msg.bbox.center.position.x = bbox_x
            det_msg.bbox.center.position.y = bbox_y
            det_msg.bbox.size_x = bbox_w
            det_msg.bbox.size_y = bbox_h
            
            # Publish host position to tracking node
            self.publisher_.publish(det_msg)
            
            # Draw overlay on frame for monitor/debug view
            cv2.rectangle(frame, (int(bbox_x - bbox_w/2), int(bbox_y - bbox_h/2)), 
                          (int(bbox_x + bbox_w/2), int(bbox_y + bbox_h/2)), (0, 255, 0), 2)
            cv2.putText(frame, f"HOST: {self.host_name}", (int(bbox_x - bbox_w/2), int(bbox_y - bbox_h/2 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # Output to monitor (can be disabled in production launch files)
        cv2.imshow("ROS 2 Host Recognition Monitor", frame)
        cv2.waitKey(1)

def main(args=None):
    rclpy.init(args=args)
    node = PersonDetectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        cv2.destroyAllWindows()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
