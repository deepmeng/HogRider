# Copyright (c) 2017 Microsoft Corporation.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
#  TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ===================================================================================================================

from __future__ import division

import sys
import time
from time import sleep
from collections import namedtuple
#from tkinter import ttk, Canvas, W
if sys.version_info.major == 2:
    from Tkinter import Canvas, W
    import ttk
else:
    from tkinter import ttk, Canvas, W


import numpy as np
import random
from common import visualize_training, Entity, ENV_TARGET_NAMES, ENV_ENTITIES, ENV_AGENT_NAMES, \
    ENV_ACTIONS, ENV_CAUGHT_REWARD, ENV_BOARD_SHAPE
from six.moves import range

from malmopy.agent import AStarAgent
from malmopy.agent import QLearnerAgent, BaseAgent, RandomAgent
from malmopy.agent.gui import GuiAgent
from json import dump

P_RANDOM = 0.5
P_EXIT = 0.5
P_DERROR = 0.3
P_INITR = 0.25
P_SURER = 0.75
EXP_SCORE = 13
EXP_STEPS = 725
EXP_REWARD = 725*1.8
SLEEP_S = 3
SLEEP_L = 50
VALID_POS = [
    (2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
    (2, 3), (4, 3), (6, 3),
    (2, 4), (3, 4), (4, 4), (5, 4), (6, 4),
    (2, 5), (4, 5), (6, 5),
    (2, 6), (3, 6), (4, 6), (5, 6), (6, 6), (1, 4), (7, 4) ]

# set the initial Q function and learn with 4 exploration approaches
# store the updated Q function
EXPL_OPT = 4
#learning rate
GAMMA = 0.9 

class HogRiderQAgent(BaseAgent):
    """HogRider agent - heuristic with history."""


    def __init__(self, name, visualizer=None):

        nb_actions = len(ENV_ACTIONS)
        super(HogRiderQAgent, self).__init__(name, nb_actions, visualizer = visualizer)

        self.current_agent = HogRiderAgent1(name, ENV_TARGET_NAMES[0],
                                         visualizer = visualizer)

    def act(self, new_state, reward, done, is_training=False):
        return self.current_agent.act(new_state, reward, done, is_training)

    def save(self, out_dir):
        self.current_agent.save(out_dir)

    def load(self, out_dir):
        self.current_agent(out_dir)

    def inject_summaries(self, idx):
        self.current_agent.inject_summaries(idx)
        
class HogRiderAgent1(AStarAgent):
    ACTIONS = ENV_ACTIONS

    def __init__(self, name, target, visualizer = None):
        super(HogRiderAgent1, self).__init__(name, len(HogRiderAgent1.ACTIONS),
                                           visualizer = visualizer)
        self._target = str(target)
        # probability that you are random and one-step history 
        self._random = P_INITR
        self._random2 = P_INITR
        self._randomhis = P_INITR
        self._randomhis2 = P_INITR
        # target's previous position and #of steps without movement
        self._pretarget = [0, 0, 0]
        # your previous position and direction
        self._yourprepos = [0, 0, 0]
        # your distance to the target in last step
        self._yourdis = 20
        # my action in next step in case there is detection error 
        self._mynextaction = 0
        # accumulated steps in an episode, accumulated reward in an episode
        self._step = 0
        self._reward = 0
        # # of episodes and total reward in all episodes
        self._episode = 1
        self._totalreward = 0
        # [#episodes, #classed as random, avg steps-to-class R, total steps, #wrong obs detection, #target move]
        self._class = [[self._episode, 0, 0, 0, 0, 0]]
        # whether the action [0, 1, 2] means you are focused, anticipation from last step
        self._focus = [0, 0, 0]
        # whether I slept in last step
        self._sleepF = 0
        self._Qmatrix = np.loadtxt('rdn.txt').reshape((3,10,10,8,25,4))
        #self._Qmatrix = np.zeros((3,10,10,8,25,4))
        self._history = [[1, -1, -1, -1, -1, -1, -1]]
	self._stepCount = 0
	self._belief = [] # [episode, step(>1), belief]
	self._belief_de = [] # [episode, step(>1), belief]

    def act(self, state, reward, done, is_training=False):
        if done:
            # 1st step of an new episode, initialize some variables
            self._totalreward += self._reward + reward
            self._episode += 1
            self._class[0][0] += 1
            self._class[0][3] += self._step
            self._step = 1
            self._random = P_INITR
            self._random2 = P_INITR
            self._randomhis = P_INITR
            self._randomhis2 = P_INITR
            self._yourdis = 20
            
	    # update matrix with reward and state sequence
            self._reward += reward
            self.updateQ(self._reward)

            self._reward = 0
	    self._stepCount = 1
            self._history = [[1, -1, -1, -1, -1, -1, -1]]
        else:
            self._reward += reward
            self._step += 1
	    self._stepCount += 1
        reward = self._reward

        if state is None:
            print("No state transfered in! Return action 0!")
            self._sleepF = 1
            sleep(0.1)
            return self._mynextaction
        
        entities = state[1]
        state = state[0]

        # get the position and yaw of agents and target
        me = [(j, i) for i, v in enumerate(state) for j, k in enumerate(v) if self.name in k]
        you = [(j, i) for i, v in enumerate(state) for j, k in enumerate(v) if 'Agent_1' in k]
        target = [(j, i) for i, v in enumerate(state) for j, k in enumerate(v) if self._target in k]
        if len(me) == 0 or len(you) == 0 or len(target) == 0:
            print("Error in observation!!!")
            self._sleepF = 1
            sleep(1)
            return self._mynextaction
        
        me_details = [e for e in entities if e['name'] == self.name]
        if len(me_details) == 0:
            print("Error in observation!!!")
            self._sleepF = 1
            sleep(1)
            return self._mynextaction
        else:
            me_details = me_details[0]
        yaw = int(me_details['yaw'])
        direction = ((((yaw - 45) % 360) // 90) - 1) % 4  # convert Minecraft yaw to 0=north, 1=east etc.
        
        you_details = [e for e in entities if e['name'] == 'Agent_1']
        if len(you_details) == 0:
            print("Error in observation!!!")
            self._sleepF = 1
            sleep(1)
            return self._mynextaction
        else:
            you_details = you_details[0]           
        yaw = int(you_details['yaw'])
        you_direction = ((((yaw - 45) % 360) // 90) - 1) % 4        
		
	# if the state is wrong, return 0
        if not self.checkpos(me[0][0:2], you[0][0:2], target[0][0:2]): # error in observation
            print("Error in observation!!!")
            self._sleepF = 1
            sleep(1)
            return self._mynextaction
			
        # get the target's state and neighboors, then find the best action
        target_state, targetNb1, targetNb2 = self.targetNb(target)                 
        # compute the exit movement 
        exit1, e_move1 = self.nextaction((me[0][0], me[0][1]), direction, (1, 4))
        nextpos = self.yournextpos((me[0][0], me[0][1]), direction, e_move1)
        nextstep, e1_nextaction = self.nextaction((nextpos[0], nextpos[1]), nextpos[2], (1, 4))
        
        exit2, e_move2 = self.nextaction((me[0][0], me[0][1]), direction, (7, 4))
        nextpos = self.yournextpos((me[0][0], me[0][1]), direction, e_move2)
        nextstep, e2_nextaction = self.nextaction((nextpos[0], nextpos[1]), nextpos[2], (7, 4))
        
        e_steps = (5+reward-min(exit1, exit2)+EXP_REWARD)/(min(exit1, exit2)-reward+EXP_STEPS)  if min(exit1, exit2)-reward <= 25 else (EXP_REWARD-25)/(EXP_STEPS+25) # per-step score for exit
        s_steps = (reward-1+EXP_REWARD)/(1-reward+EXP_STEPS) # per-step score for stay
        
        # initialize my next action
        if exit1 < exit2 or (exit == exit2 and target[0][0] <= 4):
            self._mynextaction = e1_nextaction
        else:
            self._mynextaction = e2_nextaction
        
        # dis1, move1 = self.nextaction((me[0][0], me[0][1]), direction, (target[0][0], target[0][1]))
        dis1Nb1, move1Nb1 = self.nextaction((me[0][0], me[0][1]), direction, targetNb1)
        dis1Nb2, move1Nb2 = self.nextaction((me[0][0], me[0][1]), direction, targetNb2)
        
        # dis0, move0 = self.nextaction((you[0][0], you[0][1]), you_direction, (target[0][0], target[0][1]))
        dis0Nb1, move0Nb1 = self.nextaction((you[0][0], you[0][1]), you_direction, targetNb1)
        dis0Nb2, move0Nb2 = self.nextaction((you[0][0], you[0][1]), you_direction, targetNb2)

	
	stateIndex = [target_state, min(dis0Nb1,dis0Nb2), min(dis1Nb1,dis1Nb2), min(exit1,exit2)-1, int(-self._reward)]     


        # =====Exploration rules=====
        """ This expl is excluded, since it's much more slower than exploring every step """
     	q = self._Qmatrix[stateIndex[0]][stateIndex[1]][stateIndex[2]][stateIndex[3]][stateIndex[4]][:]
    	action1 = np.argmax(q)
        rdn = random.random() 
        BETA = 0.9
     	# No expl.
     	if EXPL_OPT == 1:
            action = action1
     	# Expl. all
     	elif EXPL_OPT == 2:
            if rdn < BETA:
                action = action1
            else:  
                rdn2 = random.random()
                rest_a = [i for i in range(len(q)) if i != action1]
                action = rest_a[0] if rdn < 1/3.0 else (rest_a[1] if rdn < 2/3.0 else rest_a[2])
     	# Expl. top-2
     	elif EXPL_OPT == 3:
            action2 = np.argmax([q[i] for i in range(len(q)) if i!=action1])
            action = action1 if rdn<BETA else action2
        # Expl. active learning
     	elif EXPL_OPT == 4:
            if rdn < BETA:
                action = action1
            else:                  
                tmp_q = [q[action1]-i for i in q]
                tmp_q2 = [i for i in range(len(q)) if 0<tmp_q[i]<(1+abs(q[action1]))/2.0]
                len_q2 = len(tmp_q2)
                action = action1 if len_q2==0 else (tmp_q2[0] if rdn<0.9+0.1/len_q2 else (tmp_q2[1] if rdn<0.9+2*0.1/len_q2 else tmp_q2[2]))
        # Expl. UCT
     	elif EXPL_OPT == 5:
            if self._stepCount > 1:
                action = action1
            else:
                tmp_q = [q[action1]-i for i in q]
                tmp_q = [1.0/(i+q[action1]) for i in tmp_q]
                sum_tmp_q = sum(tmp_q)
                tmp_q = [sum(tmp_q[0:(i+1)])/sum_tmp_q for i in range(len(tmp_q))]
                action = 0 if rdn<tmp_q[0] else (1 if rdn<tmp_q[1] else (2 if rdn<tmp_q[2] else 3))
        #=============================
       
        print(me[0], direction, you[0], you_direction, target[0], action)

        self._lastAction = action
        
        # store explored history
    	if self._stepCount==1:
            self._history = [[1,stateIndex[0],stateIndex[1],stateIndex[2],stateIndex[3],stateIndex[4],action]]
        else:
            self._history.append([self._stepCount,stateIndex[0],stateIndex[1],stateIndex[2],stateIndex[3],stateIndex[4],action])
     
 
        if action>1:
            print('Sleep for a while')
            self._sleepF = 1
            sleep(3)
 	if action==0 or action==2:
            if dis0Nb1<=dis0Nb2:
                action = move1Nb2
            else:
                action = move1Nb1
 	else: 
	    action = e_move1 if exit1 <= exit2 else e_move2
	    
    	self._lastState = stateIndex

        if self._episode%3000==0:
##            try:
##                filename = 'class1_r_'+str(self._episode)+'.txt'
##                with open(filename,'w') as f:
##                    np.savetxt(f, self._belief, fmt='%-7.2f')
##            
##            except Exception as e:
##                print('Unable to save the results: %s' % e)
##
##            try:
##                filename = 'class1_r_de_'+str(self._episode)+'.txt'
##                with open(filename,'w') as f:
##                    np.savetxt(f, self._belief_de, fmt='%-7.2f')
##            
##            except Exception as e:
##                print('Unable to save the results: %s' % e)
                
            try:
                filename = 'rdnEXPL'+str(EXPL_OPT)+'EP'+str(self._episode)+'.txt'
                with open(filename,'w') as f:

                    for i in range(3):
                        for j in range(10):
                            for k in range(10):
                                for l in range(8):
                                    np.savetxt(f, self._Qmatrix[i][j][k][l], fmt='%-7.2f')
            
            except Exception as e:
                print('Unable to save the results: %s' % e)

    	return action
      
        

    def updateQ(self, reward): #old, act, reward, new
        
	for i, s in enumerate(self._history):
            self._Qmatrix[s[1],s[2],s[3],s[4],s[5],s[6]] = GAMMA*self._Qmatrix[s[1],s[2],s[3],s[4],s[5],s[6]] + (1-GAMMA)*reward
            #self._Qmatrix[s[1],s[2],s[3],s[4],s[5],s[6]] = (1-ALPHA/(self._episode**GAMMA))*self._Qmatrix[s[1],s[2],s[3],s[4],s[5],s[6]] + ALPHA/(self._episode**GAMMA)*reward
  

    def checkpos(self, m, y, t):
        if ((m[0], m[1]) not in VALID_POS) or ((y[0], y[1]) not in VALID_POS) or ((t[0], t[1]) not in VALID_POS):
            self._class[0][4] += 1
            return False
        else:
            return True 

    def preaction(self, pre, now):
        # compute your last action, if there is detection error, return -1
        if pre == now: # you didn't change anything
            if self.yournextpos(pre[0:2], pre[2], 0) == now:
                return 0
            else: # wrong detection
                self._class[0][4] += 1
                return -1
        elif pre[0:2] == now[0:2]: # you only changed direction
            if now[2] == (pre[2] + 3)%4: # you turned left
                return 1
            elif now[2] == (pre[2] + 5)%4: # you turned right
                return 2
            else: # wrong detection in last step
                self._class[0][4] += 1
                return -2
        elif abs(pre[0]-now[0]) + abs(pre[1]-now[1]) == 1 and pre[2] == now[2]:
            if self.yournextpos(pre[0:2], pre[2], 0) == now:
                return 0
            else:
                self._class[0][4] += 1
                return -2
        elif abs(pre[0]-now[0]) + abs(pre[1]-now[1]) == 1 and (pre[2] + now[2])%2 == 1: # wrong detection in last step
            self._class[0][4] += 1
            return -2
        else:
            self._class[0][4] += 1
            return -1

    def sleepT(self, T):
        self._sleepF = 1
        sleep(T)
				
    def yournextpos(self, p, p_direction, p_action):
        # compute the anticipation of your next position with an action
        if p_action>0:
            # only change direction
            if p_action==1:
                p_direction = (p_direction+3)%4
            else:
                p_direction = (p_direction+1)%4
            return [p[0], p[1], p_direction]
        else:
            # move forward
            new_x = p[0] + (p_direction%2)*(2-p_direction)
            new_y = p[1] + ((p_direction+1)%2)*(p_direction-1)
            if (new_x, new_y) in VALID_POS:
                return [new_x, new_y, p_direction]
            else:
                return [p[0], p[1], p_direction]

    def nextaction(self, p1, p1_direction, p2):
        # compute the distance between the two positions and the next movement
        # self._othermove store the other possible action
        self._othermove = -1

        if p1[0]==p2[0] and p1[1]==p2[1]:
            # already reached the poistition, then just turn
            self._othermove = 2
            return 0, 1
        
        if p1[0]==p2[0]:
            if p1[0]%2==0:
                # the start and end are in the same col without pillar
                nb_steps = abs(p1[0]-p2[0])+abs(p1[1]-p2[1])
                if p1[1]>p2[1]:
                    if p1_direction==0:
                        return nb_steps, 0
                    elif p1_direction==1:
                        return nb_steps+1, 1
                    elif p1_direction==2:
                        self._othermove = 2
                        return nb_steps+2, 1
                    else:
                        return nb_steps+1, 2
                else:
                    if p1_direction==2:
                        return nb_steps, 0
                    elif p1_direction==3:
                        return nb_steps+1, 1
                    elif p1_direction==0:
                        self._othermove = 2
                        return nb_steps+2, 1
                    else:
                        return nb_steps+1, 2                
            else:
                # the start and end are in the same col with pillar
                nb_steps = abs(p1[0]-p2[0])+abs(p1[1]-p2[1])+4
                if p1_direction%2==0:
                    self._othermove = 2
                    return nb_steps+1, 1
                else:
                    return nb_steps, 0
            
        elif p1[1]==p2[1]:
            if p1[1]%2==0:
                # the start and end are in the same row without pillar
                nb_steps = abs(p1[0]-p2[0])+abs(p1[1]-p2[1])
                if p1[0]>p2[0]:
                    if p1_direction==3:
                        return nb_steps, 0
                    elif p1_direction==0:
                        return nb_steps+1, 1
                    elif p1_direction==1:
                        self._othermove = 2
                        return nb_steps+2, 1
                    else:
                        return nb_steps+1, 2
                else:
                    if p1_direction==1:
                        return nb_steps, 0
                    elif p1_direction==2:
                        return nb_steps+1, 1
                    elif p1_direction==3:
                        self._othermove = 2
                        return nb_steps+2, 1
                    else:
                        return nb_steps+1, 2
            else:
                # the start and end are in the same row with pillar
                nb_steps = abs(p1[0]-p2[0])+abs(p1[1]-p2[1])+4
                if p1_direction%2==1:
                    self._othermove = 2
                    return nb_steps+1, 1
                else:
                    return nb_steps, 0

        elif p1[0]%2==1:
            # star at the two special cols, go east or west 
            nb_steps = abs(p1[0]-p2[0])+abs(p1[1]-p2[1])
            if p2[0]%2==1:
                # end also at the two special cols - two turns
                nb_steps += 2
            else:
                nb_steps += 1
            if p1[0]<p2[0]:
                if p1_direction==1:
                    return nb_steps, 0
                elif p1_direction==0:
                    return nb_steps+1, 2
                elif p1_direction==3:
                    self._othermove = 2
                    return nb_steps+2, 1
                else:
                    return nb_steps+1, 1
            else:
                if p1_direction==3:
                    return nb_steps, 0
                elif p1_direction==2:
                    return nb_steps+1, 2
                elif p1_direction==1:
                    self._othermove = 2
                    return nb_steps+2, 1
                else:
                    return nb_steps+1, 1

        elif p1[1]%2==1:
            # start at the two special rows, go north or south
            nb_steps = abs(p1[0]-p2[0])+abs(p1[1]-p2[1])
            if p2[1]%2==1:
                # end also at the two special rows - two turns
                nb_steps += 2
            else:
                nb_steps += 1
            if p1[1]<p2[1]:
                if p1_direction==2:
                    return nb_steps, 0
                elif p1_direction==1:
                    return nb_steps+1, 2
                elif p1_direction==0:
                    self._othermove = 2
                    return nb_steps+2, 1
                else:
                    return nb_steps+1, 1
            else:
                if p1_direction==0:
                    return nb_steps, 0
                elif p1_direction==3:
                    return nb_steps+1, 2
                elif p1_direction==2:
                    self._othermove = 2
                    return nb_steps+2, 1
                else:
                    return nb_steps+1, 1
                
        else:
            # start at the nine free positions and end not in the same row/col
            nb_steps = abs(p1[0]-p2[0])+abs(p1[1]-p2[1])+1
            if p1[0]<p2[0] and p1[1]>p2[1]:
                # go to right-up corner
                if p1[0]==6:
                    # go to the right exit from the last col, always go north
                    if p1_direction==1:
                        return nb_steps+1, 1
                    elif p1_direction==2:
                        self._othermove = 2
                        return nb_steps+2, 1
                    elif p1_direction==3:
                        return nb_steps+1, 2
                    else:
                        return nb_steps, 0
                elif p2[1]%2==1: # go right before go up
                    if p1_direction==0:
                        if p2[1]<p1[1]-1:
                            self._othermove = 0
                        return nb_steps+1, 2
                    elif p1_direction==1:
                        return nb_steps, 0
                    elif p1_direction==2:
                        return nb_steps+1, 1
                    else:
                        return nb_steps+2, 2
                elif p2[0]%2==1: # go up before go right
                    if p1_direction==0:
                        return nb_steps, 0
                    elif p1_direction==1:
                        return nb_steps+1, 1
                    elif p1_direction==3:
                        return nb_steps+1, 2
                    else:
                        self._othermove = 2
                        return nb_steps+2, 1
                elif p1_direction<=1:
                    return nb_steps, 0
                elif p1_direction==2:
                    return nb_steps+1, 1
                else:
                    return nb_steps+1, 2
            elif p1[0]<p2[0] and p1[1]<p2[1]:
                # go to right-down corner
                if p1[0]==6:
                    # go to the right exit from the last col, always go south
                    if p1_direction==1:
                        return nb_steps+1, 2
                    elif p1_direction==0:
                        self._othermove = 2
                        return nb_steps+2, 1
                    elif p1_direction==3:
                        return nb_steps+1, 1
                    else:
                        return nb_steps, 0
                elif p2[1]%2==1: # go right before go down
                    if p1_direction==0:
                        return nb_steps+1, 2
                    elif p1_direction==1:
                        return nb_steps, 0
                    elif p1_direction==2:
                        return nb_steps+1, 1
                    else:
                        if p2[1]>p1[1]+1:
                            self._othermove = 0
                        return nb_steps+2, 1
                elif p2[0]%2==1: # go down before go right
                    if p1_direction==0:
                        self._othermove = 1
                        return nb_steps+2, 2
                    elif p1_direction==1:
                        return nb_steps+1, 2
                    elif p1_direction==3:
                        return nb_steps+1, 1
                    else:
                        return nb_steps, 0
                elif p1_direction==0:
                    return nb_steps+1, 2
                elif p1_direction<=2:
                    return nb_steps, 0
                else:
                    return nb_steps+1, 1
            elif p1[0]>p2[0] and p1[1]<p2[1]:
                # go to left-down corner
                if p1[0]==2:
                    # go to the left exit from the first col, always go south
                    if p1_direction==1:
                        return nb_steps+1, 2
                    elif p1_direction==0:
                        self._othermove = 2
                        return nb_steps+2, 1
                    elif p1_direction==3:
                        return nb_steps+1, 1
                    else:
                        return nb_steps, 0
                elif p2[1]%2==1: # go left before go down
                    if p1_direction==0:
                        return nb_steps+1, 1
                    elif p1_direction==3:
                        return nb_steps, 0
                    elif p1_direction==2:
                        if p2[1]>p1[1]+1:
                            self._othermove = 0
                        return nb_steps+1, 2
                    else:
                        return nb_steps+2, 2
                elif p2[0]%2==1: # go down before go left
                    if p1_direction==0:
                        self._othermove = 2
                        return nb_steps+2, 1
                    elif p1_direction==1:
                        return nb_steps+1, 2
                    elif p1_direction==3:
                        return nb_steps+1, 1
                    else:
                        return nb_steps, 0
                elif p1_direction==0:
                    return nb_steps+1, 1
                elif p1_direction>=2:
                    return nb_steps, 0
                else:
                    return nb_steps+1, 2
            elif p1[0]>p2[0] and p1[1]>p2[1]:
                # go to left-up corner
                if p1[0]==2:
                    # go to the left exit from the first col, always go north
                    if p1_direction==1:
                        return nb_steps+1, 1
                    elif p1_direction==2:
                        self._othermove = 2
                        return nb_steps+2, 1
                    elif p1_direction==3:
                        return nb_steps+1, 2
                    else:
                        return nb_steps, 0
                elif p2[1]%2==1: # go left before go up
                    if p1_direction==0:
                        if p2[1]<p1[1]-1:
                            self._othermove = 0
                        return nb_steps+1, 1
                    elif p1_direction==3:
                        return nb_steps, 0
                    elif p1_direction==1:
                        return nb_steps+1, 1
                    else:
                        return nb_steps+1, 2
                elif p2[0]%2==1: # go up before go left
                    if p1_direction==0:
                        return nb_steps, 0
                    elif p1_direction==1:
                        return nb_steps+1, 1
                    elif p1_direction==3:
                        return nb_steps+1, 2
                    else:
                        self._othermove = 1
                        return nb_steps+2, 2
                elif p1_direction==0 or p1_direction==3:
                    return nb_steps, 0
                elif p1_direction==1:
                    return nb_steps+1, 1
                else:
                    return nb_steps+1, 2

    def targetNb(self, target):
        # get the target position and find the neighboors
        if target[0][0]*((target[0][1]+1)%2)==4:
            # the target is at a unable to caught position
            # return 0 and target's position * 2
            return 0, (target[0][0], target[0][1]), (target[0][0], target[0][1])
        elif target[0][1]*((target[0][0]+1)%2)==4:
            # the target is beside the exit, then go to the target's position
            # return 1, target's position * 2
            return 1, (target[0][0], target[0][1]), (target[0][0], target[0][1])
        elif target[0][0]==3 or target[0][0]==5:
            # return left and right position
            return 2, (target[0][0]-1, target[0][1]), (target[0][0]+1, target[0][1])
        elif target[0][1]==3 or target[0][1]==5:
            # return up and down position
            return 2, (target[0][0], target[0][1]-1), (target[0][0], target[0][1]+1)
        elif target[0][0]==2 and target[0][1]==2:
            # left-up corner
            return 2, (target[0][0], target[0][1]+1), (target[0][0]+1, target[0][1])
        elif target[0][0]==6 and target[0][1]==2:
            # right-up corner
            return 2, (target[0][0], target[0][1]+1), (target[0][0]-1, target[0][1])
        elif target[0][0]==2 and target[0][1]==6:
            # left-down corner
            return 2, (target[0][0], target[0][1]-1), (target[0][0]+1, target[0][1])
        elif target[0][0]==6 and target[0][1]==6:
            # right-down corner
            return 2, (target[0][0], target[0][1]-1), (target[0][0]-1, target[0][1])
        elif target[0][0]==1:
            # target is in the exit, return one neighboor
            return 1, (target[0][0]+1, target[0][1]), (target[0][0]+1, target[0][1])
        elif target[0][0]==7:
            # target is in the exit, return one neighboor
            return 1, (target[0][0]-1, target[0][1]), (target[0][0]-1, target[0][1])
