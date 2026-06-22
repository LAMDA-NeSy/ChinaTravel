import time
from chinatravel.agent.base import BaseAgent

class TPCAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="TPC", **kwargs)
    
    def run(self, query, prob_idx, oralce_translation=False):


        self.reset_clock()

        result = {
            "itinerary": [], 
            "elapsed_time(sec)": time.time() - self.start_clock, 
            }
        
        return False, result
