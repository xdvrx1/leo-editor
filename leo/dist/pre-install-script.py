#@+leo-ver=4-thin
#@+node:ekr.20080827092958.3:@thin pre-install-script.py
import sys
print ("This is Leo's pre-install script")
print ("sys.executable: %s" % sys.executable)
# print ("dir(sys): %s" % dir(sys))
print ("sys.path")
for z in sys.path: print z
print sys.argv # Generates an error so I can see results.
# print ("sys.argv...")
# for z in sys.argv:
    # print z
#@nonl
#@-node:ekr.20080827092958.3:@thin pre-install-script.py
#@-leo
