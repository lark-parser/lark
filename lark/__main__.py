import sys
import pickle
cnffi = open('larkconfg','wb')
if sys.argv[0]:
    pickle.dump(cnffi, True)
else:
    pickle.dump(cnffi, False)
    
