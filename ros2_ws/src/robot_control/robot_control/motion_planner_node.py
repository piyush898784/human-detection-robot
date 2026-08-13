import rclpy
from rclpy.node import Node
from vision_msgs.msg import Detection2D
from geometry_msgs.msg import Twist
import json
import threading
import time

# Optional: pip install websocket-client
try:
    import websocket
except ImportError:
    websocket = None

class MotionPlannerNode(Node):
    def __init__(self):
        super().__init__('motion_planner_node')
        
        # Subscriptions and Publishers
        self.subscription = self.create_subscription(
            Detection2D,
            '/vision/host_identified',
            self.host_callback,
            10
        )
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        
        # Target frame center (assumed 800x600 resolution stream from ESP32-CAM)
        self.frame_width = 800
        self.frame_height = 600
        self.center_x = self.frame_width / 2.0
        self.target_bbox_area = 30000.0  # Bounding box target area corresponding to ~1.2 meters safe following distance
        
        # PID Constants
        self.Kp_yaw = 0.003
        self.Ki_yaw = 0.0001
        self.Kd_yaw = 0.0005
        
        self.Kp_dist = 0.00002
        self.Ki_dist = 0.0000005
        self.Kd_dist = 0.000005
        
        # Error integrators & derivatives
        self.prev_err_yaw = 0.0
        self.integral_yaw = 0.0
        self.prev_err_dist = 0.0
        self.integral_dist = 0.0
        
        # Time tracker
        self.last_time = time.time()
        
        # WebSocket connection to LILYGO ESP32 softAP IP
        self.ws_url = "ws://192.168.4.1:80/"
        self.ws = None
        self.ws_connected = False
        
        # Connect in a separate thread to avoid blocking ROS 2 executor
        threading.Thread(target=self.connect_websocket, daemon=True).start()
        
        self.get_logger().info("Motion Planner & PID Control Node Initialized.")

    def connect_websocket(self):
        if websocket is None:
            self.get_logger().warn("websocket-client library not installed. Skipping WebSocket output.")
            return

        while rclpy.ok():
            try:
                self.get_logger().info(f"Connecting to actuator LILYGO WebSockets: {self.ws_url}")
                self.ws = websocket.create_connection(self.ws_url, timeout=3.0)
                self.ws_connected = True
                self.get_logger().info("Successfully connected to actuator controller.")
                break
            except Exception as e:
                self.get_logger().warn(f"Actuator connection failed: {e}. Retrying in 3.0s...")
                time.sleep(3.0)

    def host_callback(self, msg):
        current_time = time.time()
        dt = current_time - self.last_time
        if dt <= 0.0:
            dt = 0.01
        self.last_time = current_time

        # Extract detected bounding box
        bbox_x = msg.bbox.center.position.x
        bbox_y = msg.bbox.center.position.y
        bbox_w = msg.bbox.size_x
        bbox_h = msg.bbox.size_y
        current_area = bbox_w * bbox_h
        
        # 1. Compute Yaw (Rotation) PID
        error_yaw = self.center_x - bbox_x  # Pixel deviation from center
        self.integral_yaw += error_yaw * dt
        derivative_yaw = (error_yaw - self.prev_err_yaw) / dt
        yaw_vel = (self.Kp_yaw * error_yaw) + (self.Ki_yaw * self.integral_yaw) + (self.Kd_yaw * derivative_yaw)
        self.prev_err_yaw = error_yaw
        
        # 2. Compute Linear Distance (Forward/Backward) PID
        error_dist = self.target_bbox_area - current_area
        self.integral_dist += error_dist * dt
        derivative_dist = (error_dist - self.prev_err_dist) / dt
        linear_x = (self.Kp_dist * error_dist) + (self.Ki_dist * self.integral_dist) + (self.Kd_dist * derivative_dist)
        self.prev_err_dist = error_dist

        # 3. Constrain velocities
        linear_x = max(-0.3, min(0.6, linear_x))
        yaw_vel = max(-0.8, min(0.8, yaw_vel))

        # Publish internally as geometry_msgs/Twist
        twist = Twist()
        twist.linear.x = linear_x
        twist.angular.z = yaw_vel
        self.cmd_vel_pub.publish(twist)
        
        # 4. Forward as JSON packet to LILYGO Actuator Node
        if self.ws_connected and self.ws:
            payload = {
                "x_vel": linear_x,
                "yaw_vel": yaw_vel,
                "status": "LOCK-ON"
            }
            try:
                self.ws.send(json.dumps(payload))
            except Exception as e:
                self.get_logger().error(f"Failed to transmit packet: {e}")
                self.ws_connected = False
                threading.Thread(target=self.connect_websocket, daemon=True).start()

def main(args=None):
    rclpy.init(args=args)
    node = MotionPlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.ws:
            node.ws.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
