import numpy as np
import xml.etree.ElementTree as ET
from MujocoManip.models.base import MujocoXML
from MujocoManip.miscellaneous import XMLError
from MujocoManip.models.world import MujocoWorldBase
from MujocoManip.models.model_util import *
from MujocoManip.miscellaneous.utils import *


class ObjectPositionSampler(object):
    def __init__(self, mujoco_objects, table_top_offset, table_size):
        """
        Args:
            Mujoco_objcts(MujocoObject * n_obj): object to be placed
            table_top_offset(float * 3): location of table top center
            table_size(float * 3): x,y,z-halfsize of the table
        """
        self.mujoco_objects = mujoco_objects
        self.n_obj = len(self.mujoco_objects)
        self.table_top_offset = table_top_offset
        self.table_size = table_size

    def sample(self):
        """
        Args:
            object_index: index of the current object being sampled
        Returns:
            xpos((float * 3) * n_obj): x,y,z position of the objects in world frame
            xquat((float * 4) * n_obj): quaternion of the objects
        """
        raise NotImplementedError

class UniformRandomSampler(ObjectPositionSampler):
    """
        Places all objects within the table uniformly random
    """
    def __init__(self, mujoco_objects, table_top_offset, table_size):
        super().__init__(mujoco_objects, table_top_offset, table_size)

    def sample(self):
        pos_arr = []
        quat_arr = []
        placed_objects = []
        index = 0
        for obj_mjcf in self.mujoco_objects:
            horizontal_radius = obj_mjcf.get_horizontal_radius()
            bottom_offset = obj_mjcf.get_bottom_offset()
            success = False
            for i in range(1000): # 1000 retries
                table_x_half = self.table_size[0] / 2 - horizontal_radius
                table_y_half = self.table_size[1] / 2 - horizontal_radius
                object_x = np.random.uniform(high=table_x_half, low=-table_x_half)
                object_y = np.random.uniform(high=table_y_half, low=-1 * table_y_half)
                # objects cannot overlap
                location_valid = True
                for (x, y, z), r in placed_objects:
                    if np.linalg.norm([object_x - x, object_y - y], 2) <= r + horizontal_radius:
                        location_valid = False
                        break
                if location_valid: 
                    # location is valid, put the object down
                    pos = self.table_top_offset - bottom_offset + np.array([object_x, object_y, 0])
                    placed_objects.append((pos, horizontal_radius))
                    # random z-rotation
                    rot_angle = np.random.uniform(high=2 * np.pi,low=0)
                    quat = [np.cos(rot_angle / 2), 0, 0, np.sin(rot_angle / 2)]
                    quat_arr.append(quat)
                    pos_arr.append(pos)
                    success = True
                    break
                
                # bad luck, reroll
            if not success:
                raise RandomizationError('Cannot place all objects on the desk')
            index += 1
        return pos_arr, quat_arr


class TableTopTask(MujocoWorldBase):

    """
        Table top manipulation task can be specified 
        by three elements of the environment.
        @mujoco_arena, MJCF robot workspace (e.g., table top)
        @mujoco_robot, MJCF robot model
        @mujoco_objects, a list of MJCF objects of interest
    """

    def __init__(self, mujoco_arena, mujoco_robot, mujoco_objects, Initializer=None):
        super().__init__()
        self.merge_arena(mujoco_arena)
        self.merge_robot(mujoco_robot)
        self.merge_objects(mujoco_objects)
        if Initializer is None:
            Initializer = UniformRandomSampler
        mjcfs = [x for _, x in self.mujoco_objects.items()]
        self.initializer = Initializer(mjcfs, self.table_top_offset, self.table_size)

    def merge_robot(self, mujoco_robot):
        self.robot = mujoco_robot
        self.merge(mujoco_robot)

    def merge_arena(self, mujoco_arena):
        self.arena = mujoco_arena
        self.table_top_offset = mujoco_arena.table_top_abs
        self.table_size = mujoco_arena.full_size
        self.merge(mujoco_arena)

    def merge_objects(self, mujoco_objects):
        self.n_objects = len(mujoco_objects)
        self.mujoco_objects = mujoco_objects
        self.objects = [] # xml manifestation
        self.targets = [] # xml manifestation
        self.max_horizontal_radius = 0

        for obj_name, obj_mjcf in mujoco_objects.items():
            self.merge_asset(obj_mjcf)
            # Load object
            obj = obj_mjcf.get_collision(name=obj_name, site=True)
            obj.append(joint(name=obj_name, type='free'))
            self.objects.append(obj)
            self.worldbody.append(obj)

            self.max_horizontal_radius = max(self.max_horizontal_radius,
                                             obj_mjcf.get_horizontal_radius())

    def place_objects(self):
        """
        Place objects randomly until no more collisions or max iterations hit.
        Args:
            position_sampler: generate random positions to put objects
        """
        pos_arr, quat_arr = self.initializer.sample()
        for i in range(len(self.objects)):
            self.objects[i].set('pos', array_to_string(pos_arr[i]))
            self.objects[i].set('quat', array_to_string(quat_arr[i]))
        # placed_objects = []
        # index = 0
        # for _, obj_mjcf in self.mujoco_objects.items():
        #     horizontal_radius = obj_mjcf.get_horizontal_radius()
        #     bottom_offset = obj_mjcf.get_bottom_offset()
        #     success = False
        #     for i in range(1000): # 1000 retries
        #         table_x_half = self.table_size[0] / 2 - horizontal_radius
        #         table_y_half = self.table_size[1] / 2 - horizontal_radius
        #         object_x = np.random.uniform(high=table_x_half, low=-table_x_half)
        #         object_y = np.random.uniform(high=table_y_half, low=-1 * table_y_half)
        #         # objects cannot overlap
        #         location_valid = True
        #         for (x, y, z), r in placed_objects:
        #             if np.linalg.norm([object_x - x, object_y - y], 2) <= r + horizontal_radius:
        #                 location_valid = False
        #                 break
        #         if location_valid: 
        #             # location is valid, put the object down
        #             pos = self.table_top_offset - bottom_offset + np.array([object_x, object_y, 0])
        #             placed_objects.append((pos, horizontal_radius))
        #             # random z-rotation
        #             rot_angle = np.random.uniform(high=2 * np.pi,low=0)
        #             quat = array_to_string([np.cos(rot_angle / 2), 0, 0, np.sin(rot_angle / 2)])
        #             self.objects[index].set('quat', quat)
        #             self.objects[index].set('pos', array_to_string(pos))
        #             success = True
        #             break
                
        #         # bad luck, reroll
        #     if not success:
        #         raise RandomizationError('Cannot place all objects on the desk')
        #     index += 1
