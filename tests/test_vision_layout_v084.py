import tkinter as tk
import unittest
from visionbot.ui_layout import layout_mode, shortcut_edge, StableStringVar

class LayoutTests(unittest.TestCase):
    def test_breakpoint_hysteresis(self):
        self.assertEqual(layout_mode(1280,840), (True,False))
        self.assertEqual(layout_mode(1050,840,(True,False)), (True,False))
        self.assertEqual(layout_mode(1050,840,(False,False)), (False,False))
        self.assertEqual(layout_mode(550,650), (False,True))
        self.assertEqual(layout_mode(1280,750,(True,True)), (True,True))
        self.assertEqual(layout_mode(1280,790,(True,True)), (True,False))

    def test_no_repeat_or_right_alt(self):
        action, held=shortcut_edge(True,False,False,True,False,(False,False))
        self.assertEqual(action,1)
        self.assertIsNone(shortcut_edge(True,False,False,True,False,held)[0])
        self.assertEqual(shortcut_edge(True,False,False,False,True,(False,False))[0],2)
        self.assertIsNone(shortcut_edge(False,True,False,True,False,(False,False))[0])
        self.assertIsNone(shortcut_edge(True,False,True,False,True,(False,False))[0])
        self.assertIsNone(shortcut_edge(True,False,False,True,True,(False,False))[0])

    def test_stable_variable_does_not_redraw_on_same_value(self):
        interp=tk.Tcl()
        var=StableStringVar(master=interp,value='idle')
        calls=[]
        var.trace_add('write',lambda *_:calls.append(var.get()))
        var.set('idle');var.set('ready');var.set('ready')
        self.assertEqual(calls,['ready'])

if __name__=='__main__':unittest.main()
