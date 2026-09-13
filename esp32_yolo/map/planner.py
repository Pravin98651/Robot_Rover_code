import heapq
import math

class AStarPlanner:
    def __init__(self, resolution=1.0):
        # resolution determines how many meters each grid cell represents
        self.resolution = resolution

    def heuristic(self, a, b):
        return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

    def get_neighbors(self, node, grid, min_x, min_y, max_x, max_y):
        neighbors = []
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        for dx, dy in directions:
            nx, ny = node[0] + dx, node[1] + dy
            if min_x <= nx <= max_x and min_y <= ny <= max_y:
                cost = grid.get((nx, ny), 1.0) # default cost 1.0 (free)
                if cost < float('inf'):
                    move_cost = math.sqrt(dx**2 + dy**2) * cost
                    neighbors.append(((nx, ny), move_cost))
        return neighbors

    def plan(self, start_m, goal_m, grid, min_m=(-50, -50), max_m=(50, 50)):
        start_idx = (int(round(start_m[0] / self.resolution)), int(round(start_m[1] / self.resolution)))
        goal_idx = (int(round(goal_m[0] / self.resolution)), int(round(goal_m[1] / self.resolution)))
        
        min_x = int(min_m[0] / self.resolution)
        min_y = int(min_m[1] / self.resolution)
        max_x = int(max_m[0] / self.resolution)
        max_y = int(max_m[1] / self.resolution)

        if grid.get(goal_idx, 1.0) == float('inf'):
            return [] # Goal is blocked

        frontier = []
        heapq.heappush(frontier, (0, start_idx))
        came_from = {}
        cost_so_far = {}
        came_from[start_idx] = None
        cost_so_far[start_idx] = 0

        while frontier:
            current_cost, current = heapq.heappop(frontier)

            if current == goal_idx:
                break

            for next_node, move_cost in self.get_neighbors(current, grid, min_x, min_y, max_x, max_y):
                new_cost = cost_so_far[current] + move_cost
                if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                    cost_so_far[next_node] = new_cost
                    priority = new_cost + self.heuristic(goal_idx, next_node)
                    heapq.heappush(frontier, (priority, next_node))
                    came_from[next_node] = current

        if goal_idx not in came_from:
            return []

        path_idx = []
        current = goal_idx
        while current != start_idx:
            path_idx.append(current)
            current = came_from[current]
        path_idx.reverse()

        # Include start to ensure a smooth line
        # path_idx = [start_idx] + path_idx

        path_m = [{"x": x * self.resolution, "y": y * self.resolution} for x, y in path_idx]
        return path_m
