

class WeightedAvg:
    def __init__(self, maxSamples=10):
        self.samples = []
        self.maxSamples = maxSamples
    
    def add(self, newSample):
        newSample = float(newSample)
        self.samples.append(newSample)	
        while len(self.samples) > self.maxSamples:
            self.samples.pop(0)
        weightedSamples = self.samples + ([newSample] * 2)
        return sum(weightedSamples) / len(weightedSamples)

