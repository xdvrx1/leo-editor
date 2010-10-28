#@+leo-ver=5-thin
#@+node:ekr.20060621123339: * @file examples/print_cp.py
#@+<< docstring >>
#@+node:ekr.20060621123339.1: ** << docstring >>
'''A plugin showing how to convert an @button node to a plugin.

This plugin registers the 'print-cp' minibuffer command.'''
#@-<< docstring >>

__version__ = '0.1'
#@+<< version history >>
#@+node:ekr.20060621123339.2: ** << version history >>
#@@killcolor
#@+at
# 
# v 0.1: Initial version.
#@-<< version history >>

#@+<< imports >>
#@+node:ekr.20060621123339.3: ** << imports >>
import leo.core.leoGlobals as g

if 0:
    Pmw = g.importExtension('Pmw',    pluginName=__name__,verbose=True,required=True)
    Tk  = g.importExtension('Tkinter',pluginName=__name__,verbose=True,required=True)

# Whatever other imports your plugins uses.
#@-<< imports >>

#@+others
#@+node:ekr.20060621123339.4: ** init
def init ():

    if g.app.gui is None:
        g.app.createTkGui(__file__)

    ok = g.app.gui.guiName() == "tkinter"

    if ok:
        # g.registerHandler('after-create-leo-frame',onCreate)
        g.registerHandler(('new','open2'),onCreate)

    return ok
#@+node:ekr.20060621123339.5: ** onCreate
def onCreate (tag, keys):

    c = keys.get('c')
    if not c: return

    thePluginController = pluginController(c)
#@+node:ekr.20060621123339.6: ** class pluginController
class pluginController:

    #@+others
    #@+node:ekr.20060621123339.7: *3* __init__
    def __init__ (self,c):
        self.c = c
        c.k.registerCommand('print-cp',shortcut=None,func=self.print_cp)
        script = "c.k.simulateCommand('print-cp')"
        g.app.gui.makeScriptButton(c,script=script,buttonText='Print c & p',bg='red')
    #@+node:ekr.20060621124649: *3* print_cp
    def print_cp (self,event=None):

        c = self.c ; p = c.p
        g.es_print('c: %s' % (c.fileName()),color='red')
        g.es_print('p: %s' % (p.h),color='red')
    #@-others
#@-others
#@-leo
