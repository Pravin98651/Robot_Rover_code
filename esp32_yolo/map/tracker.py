import time
import math
import random
from planner import AStarPlanner

class SurvivorTracker:
    def __init__(self):
        self.survivors = {}
        self.next_survivor_id = 1
        
        self.robot_pose = {
            "x": 0.0,
            "y": 0.0,
            "heading": 90.0,
            "trajectory": [{"x": 0.0, "y": 0.0, "timestamp": time.time()}]
        }
        
        self.battery = 100.0
        self.energy_used = 0.0
        self.total_distance = 0.0
        self.replans = 0
        
        self.max_trajectory = 5000
        self.timeout_temporarily_lost = 2.0
        self.timeout_lost = 10.0
        
        self.start_time = time.time()
        
        # Grid and Planning
        self.planner = AStarPlanner(resolution=1.0)
        self.occupancy_grid = {} 
        self.obstacles_m = [] 
        self.moving_obstacles = [] # List of {"id", "x", "y", "vx", "vy", "radius"}
        
        self.planned_path = []
        self.target_survivor_id = None
        
        self.robot_speed = 1.0 # 10m/s simulation speed at 10Hz tick
        
        self.latest_planning_time_ms = 0

    def spawn_obstacle(self, x, y, size=1):
        self.obstacles_m.append({"x": x, "y": y, "size": size})
        idx_x = int(round(x / self.planner.resolution))
        idx_y = int(round(y / self.planner.resolution))
        
        for dx in range(-size, size+1):
            for dy in range(-size, size+1):
                self.occupancy_grid[(idx_x + dx, idx_y + dy)] = float('inf')
                
        self.replans += 1
        self.plan_path()

    def block_path(self):
        dist = 3.0
        bx = self.robot_pose["x"] + dist * math.cos(math.radians(self.robot_pose["heading"]))
        by = self.robot_pose["y"] + dist * math.sin(math.radians(self.robot_pose["heading"]))
        self.spawn_obstacle(bx, by, size=2)

    def spawn_moving_hazard(self):
        dist = 10.0
        # Spawn off to the side, moving towards the robot's general path
        angle = math.radians(self.robot_pose["heading"] + random.choice([45, -45, 90, -90]))
        hx = self.robot_pose["x"] + dist * math.cos(angle)
        hy = self.robot_pose["y"] + dist * math.sin(angle)
        
        # Aim roughly at where the robot is or slightly ahead
        target_x = self.robot_pose["x"] + 2 * math.cos(math.radians(self.robot_pose["heading"]))
        target_y = self.robot_pose["y"] + 2 * math.sin(math.radians(self.robot_pose["heading"]))
        
        move_angle = math.atan2(target_y - hy, target_x - hx)
        speed = 2.0 # Move relatively fast
        
        hazard = {
            "id": f"H{len(self.moving_obstacles)}",
            "x": hx,
            "y": hy,
            "vx": speed * math.cos(move_angle),
            "vy": speed * math.sin(move_angle),
            "radius": 1.5
        }
        self.moving_obstacles.append(hazard)

    def plan_path(self):
        if not self.target_survivor_id or self.target_survivor_id not in self.survivors:
            self.planned_path = []
            return
            
        target = self.survivors[self.target_survivor_id]
        if not target.get("location"):
            return
            
        start_m = (self.robot_pose["x"], self.robot_pose["y"])
        goal_m = (target["location"]["x"], target["location"]["y"])
        
        # Inject current positions of moving obstacles into a temporary grid copy
        # so A* routes around them.
        grid_copy = self.occupancy_grid.copy()
        for h in self.moving_obstacles:
            # Block current position and slightly ahead
            hx_idx = int(round(h["x"] / self.planner.resolution))
            hy_idx = int(round(h["y"] / self.planner.resolution))
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    grid_copy[(hx_idx + dx, hy_idx + dy)] = float('inf')
                    
            # Block predicted future position (1 sec ahead)
            fx_idx = int(round((h["x"] + h["vx"]) / self.planner.resolution))
            fy_idx = int(round((h["y"] + h["vy"]) / self.planner.resolution))
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    grid_copy[(fx_idx + dx, fy_idx + dy)] = float('inf')
        
        t0 = time.time()
        path = self.planner.plan(start_m, goal_m, grid_copy)
        t1 = time.time()
        
        self.planned_path = path
        self.latest_planning_time_ms = int((t1 - t0) * 1000)

    def predict_collision(self):
        if not self.planned_path: return False
        
        for h in self.moving_obstacles:
            # Check if moving hazard is near the immediate planned path
            for i in range(min(5, len(self.planned_path))):
                pt = self.planned_path[i]
                # Predict hazard position at future step i
                dt = i * 0.1 # assuming 1 step per tick (10Hz)
                pred_x = h["x"] + h["vx"] * dt
                pred_y = h["y"] + h["vy"] * dt
                
                dist = math.sqrt((pt["x"] - pred_x)**2 + (pt["y"] - pred_y)**2)
                if dist < h["radius"] + 1.0: # 1.0m safety margin
                    return True
        return False

    def move_robot(self):
        # Update moving hazards
        for h in self.moving_obstacles:
            h["x"] += h["vx"] * 0.1 # 10Hz tick
            h["y"] += h["vy"] * 0.1

        # Predictive replanning
        if self.predict_collision():
            self.replans += 1
            self.plan_path()

        if not self.planned_path:
            return
            
        target_pt = self.planned_path[0]
        dx = target_pt["x"] - self.robot_pose["x"]
        dy = target_pt["y"] - self.robot_pose["y"]
        dist = math.sqrt(dx**2 + dy**2)
        
        if dist < 0.5:
            self.planned_path.pop(0)
            if not self.planned_path:
                return 
            target_pt = self.planned_path[0]
            dx = target_pt["x"] - self.robot_pose["x"]
            dy = target_pt["y"] - self.robot_pose["y"]
            dist = math.sqrt(dx**2 + dy**2)
            
        target_heading = math.degrees(math.atan2(dy, dx))
        
        # Smooth turning
        diff = (target_heading - self.robot_pose["heading"]) % 360
        if diff > 180: diff -= 360
        self.robot_pose["heading"] += diff * 0.5 
        
        step = min(self.robot_speed, dist)
        self.robot_pose["x"] += step * math.cos(math.radians(self.robot_pose["heading"]))
        self.robot_pose["y"] += step * math.sin(math.radians(self.robot_pose["heading"]))
        
        self.total_distance += step
        
        idx_x = int(round(self.robot_pose["x"] / self.planner.resolution))
        idx_y = int(round(self.robot_pose["y"] / self.planner.resolution))
        terrain_cost = self.occupancy_grid.get((idx_x, idx_y), 1.0)
        
        energy_step = (step * 0.05) * terrain_cost
        self.energy_used += energy_step
        self.battery = max(0.0, 100.0 - self.energy_used)

    def get_state(self):
        active_targets = sum(1 for s in self.survivors.values() if s["status"] in ["TRACKING", "ASSESSED"])
        return {
            "survivors": list(self.survivors.values()),
            "robot": self.robot_pose,
            "obstacles": self.obstacles_m,
            "moving_obstacles": self.moving_obstacles,
            "planned_path": self.planned_path,
            "stats": {
                "total_survivors": len(self.survivors),
                "active_targets": active_targets,
                "mission_duration": int(time.time() - self.start_time),
                "battery": round(self.battery, 1),
                "distance": round(self.total_distance, 1),
                "replans": self.replans,
                "planning_time_ms": self.latest_planning_time_ms
            }
        }

    def update(self, detections):
        now = time.time()
        self.move_robot()
            
        if len(self.robot_pose["trajectory"]) == 0 or now - self.robot_pose["trajectory"][-1]["timestamp"] > 1.0:
            self.robot_pose["trajectory"].append({
                "x": self.robot_pose["x"],
                "y": self.robot_pose["y"],
                "timestamp": now
            })
            if len(self.robot_pose["trajectory"]) > self.max_trajectory:
                self.robot_pose["trajectory"].pop(0)

        matched_survivors = set()
        
        for det in detections:
            track_id = det.get("track_id", -1)
            
            survivor = None
            if track_id != -1:
                for s in self.survivors.values():
                    if s["track_id"] == track_id:
                        survivor = s
                        break
            
            if survivor is None:
                survivor_id = f"P{self.next_survivor_id}"
                self.next_survivor_id += 1
                survivor = {
                    "id": survivor_id,
                    "track_id": track_id,
                    "first_seen": now,
                    "observation_count": 0,
                    "history": []
                }
                self.survivors[survivor_id] = survivor
                
                if self.target_survivor_id is None:
                    self.target_survivor_id = survivor_id
            
            matched_survivors.add(survivor["id"])
            survivor["last_seen"] = now
            survivor["observation_count"] += 1
            survivor["confidence"] = det["confidence"]
            
            dx = det["x"] - 0.5
            angle_offset = dx * 60 
            abs_angle = math.radians(self.robot_pose["heading"] + angle_offset)
            est_dist = 1.0 / max(det["h"], 0.1) * 3.0 
            
            map_x = self.robot_pose["x"] + est_dist * math.cos(abs_angle)
            map_y = self.robot_pose["y"] + est_dist * math.sin(abs_angle)
            
            if "location" not in survivor:
                survivor["location"] = {"x": map_x, "y": map_y}
                if survivor["id"] == self.target_survivor_id:
                    self.plan_path()
            else:
                survivor["location"]["x"] = survivor["location"]["x"] * 0.9 + map_x * 0.1
                survivor["location"]["y"] = survivor["location"]["y"] * 0.9 + map_y * 0.1
            
            if len(survivor["history"]) == 0 or now - survivor["history"][-1]["timestamp"] > 1.0:
                survivor["history"].append({
                    "x": survivor["location"]["x"],
                    "y": survivor["location"]["y"],
                    "confidence": det["confidence"],
                    "timestamp": now
                })
                if len(survivor["history"]) > 100:
                    survivor["history"].pop(0)

            if survivor["observation_count"] > 20:
                survivor["priority"] = "HIGH"
            elif survivor["observation_count"] > 5:
                survivor["priority"] = "MEDIUM"
            else:
                survivor["priority"] = "LOW"
                
            survivor["status"] = "TRACKING"
            
        for sid, survivor in self.survivors.items():
            if sid not in matched_survivors:
                time_since_seen = now - survivor["last_seen"]
                if time_since_seen > self.timeout_lost:
                    survivor["status"] = "LOST"
                elif time_since_seen > self.timeout_temporarily_lost:
                    survivor["status"] = "TEMPORARILY_LOST"
                    
        if self.target_survivor_id and not self.planned_path and random.random() < 0.1:
            self.plan_path()
