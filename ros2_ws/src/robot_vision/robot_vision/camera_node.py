import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import cv2
from cv_bridge import CvBridge

class CameraNode(Node):
    def __init__(self):
        super().__init__('camera_node')
        self.publisher_ = self.create_publisher(Image, '/camera/image_raw', 10)
        self.bridge = CvBridge()
        
        # Configure streaming parameters
        self.stream_url = 'http://192.168.4.1:81/stream' # Default ESP32-CAM Access Point IP
        self.get_logger().info(f"Connecting to ESP32-CAM stream: {self.stream_url}")
        
        self.cap = cv2.VideoCapture(self.stream_url)
        self.timer = self.create_timer(0.04, self.timer_callback) # ~25 FPS

    def timer_callback(self):
        if not self.cap.isOpened():
            self.get_logger().error("Stream disconnected. Attempting to reconnect...")
            self.cap.open(self.stream_url)
            return

        ret, frame = self.cap.read()
        if ret:
            # Publish image to ROS 2 topic
            msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            self.publisher_.publish(msg)
        else:
            self.get_logger().warn("Failed to retrieve frame from camera stream.")

    def destroy_node(self):
        self.cap.release()
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = CameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
