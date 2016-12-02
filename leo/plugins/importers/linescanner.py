#@+leo-ver=5-thin
#@+node:ekr.20161108125620.1: * @file importers/linescanner.py
#@+<< linescanner docstring >>
#@+node:ekr.20161108125805.1: ** << linescanner docstring >>
'''
#@@language rest
#@@wrap

**Overview**

Leo's import infrastructure in `leoImport.py` instantiates the
Importer instance and calls `i.run`, which calls `i.scan_lines`.

New importers copy entire lines from the input file to Leo nodes. This
makes the new importers much less error prone than the legacy
(character-by-character) importers.

New importers know *nothing* about parsing. They know only about how to
scan tokens *accurately*.

**Writing a new importer**

Just run the importer;; abbreviation!

To make the importer importer;; functional you must:

1. Copy it from leoSettings (@settings-->Abbreviations-->@outline-data tree-abbreviations) to the corresponding location in myLeoSettings.leo.

2. Make sure @bool scripting-abbreviations is True in myLeoSettings.leo.

**Using the abbreviation**

1. Just type importer;; in the body pane of an empty node.

A dialog will prompt you for the name of the language.  Suppose you type x.

2. Now you will be prompted for to fill in the first field::

    'extensions': [comma-separated lists of extensions, with leading periods],

The italicized field will be highlighted.  Type '.x' (including quotes) followed by two commas.

3. You will then be prompted to fill in the second field::

    strict = True leading whitespace is significant. Otherwise False,

Again, the italicized field will be highlighted.

Type False, followed by two commas.

4. You will then be prompted for the last field::

    return level
        ### Examples:
        # self.indent # for python, coffeescript.
        # self.curlies
        # (self, curlies, self.parens)
   
Only "level" is highlighted. The comments provide some hints about what to type.

Let's type "self.curlies" followed by two commas.

5. Nothing more is highlighted, so that's it! No more substitutions remain.
   The outline is ready to use!

Take a look at the result. The new tree is an almost complete @@file node
for the importer. Subtrees contain an X_Importer class and an X_ScanState
class. Docstrings, ctors and __repr__ methods are complete.

Note: The generated tree contain ### comments showing where more work may
be needed. I might remove the need for some of them, but there is no great
need to do so.

'''
#@-<< linescanner docstring >>
#@+<< linescanner imports >>
#@+node:ekr.20161108130715.1: ** << linescanner imports >>
import leo.core.leoGlobals as g
if g.isPython3:
    import io
    StringIO = io.StringIO
else:
    import StringIO
    StringIO = StringIO.StringIO
import re
import time
#@-<< linescanner imports >>
#@+others
#@+node:ekr.20161108155730.1: ** class Importer
class Importer(object):
    '''
    The new, unified, simplified, interface to Leo's importer code.
    
    Eventually, all importers will create use this class.
    '''
    
    #@+others
    #@+node:ekr.20161108155925.1: *3* i.__init__
    #@@nobeautify

    def __init__(self,
        importCommands, 
        atAuto, # True when called from @auto logic.
        language = None, # For @language directive.
        name = None, # The kind of importer, usually the same as language
        state_class = None, # For i.scan_line
        strict = False,
    ):
        '''Importer.__init__.'''
        # Copies of args...
        self.importCommands = ic = importCommands
        self.atAuto = atAuto
        self.c = c = ic.c
        self.encoding = ic.encoding
        self.language = language or name
            # For the @language directive.
        self.name = name or language
        language = self.language
        name = self.name
        assert language and name
        assert self.language and self.name
        self.state_class = state_class
        self.strict = strict
            # True: leading whitespace is significant.

        # Set from ivars...
        self.has_decls = name not in ('xml', 'org-mode', 'vimoutliner')
        self.is_rst = name in ('rst',)
        self.tree_type = ic.treeType # '@root', '@file', etc.

        # Constants...
        data = g.set_delims_from_language(self.name)
        self.single_comment, self.block1, self.block2 = data
        self.escape = c.atFileCommands.underindentEscapeString
        self.escape_string = r'%s([0-9]+)\.' % re.escape(self.escape)
            # m.group(1) is the unindent value.
        self.escape_pattern = re.compile(self.escape_string)
        self.gen_refs = name in ('javascript',)
        self.ScanState = ScanState
            # Must be set by subclasses that use general_scan_line.
        self.tab_width = 0 # Must be set in run, using self.root.
        self.ws_pattern = re.compile(r'^\s*$|^\s*%s' % (self.single_comment or ''))

        # Settings...
        self.at_auto_warns_about_leading_whitespace = c.config.getBool(
            'at_auto_warns_about_leading_whitespace')
        self.warn_about_underindented_lines = True
        # self.at_auto_separate_non_def_nodes = False

        # State vars.
        self.errors = 0
        ic.errors = 0 # Required.
        self.parse_body = False
        self.ws_error = False
        self.root = None
    #@+node:ekr.20161110042512.1: *3* i.API for setting body text
    # All code in passes 1 and 2 *must* use this API to change body text.
    def add_line(self, p, s):
        '''Append the line s to p.v._import_lines.'''
        assert not p.b, repr(p.b)
        assert hasattr(p.v, '_import_lines'), repr(p)
        assert s, g.callers()
        assert g.isString(s), repr(s)
        p.v._import_lines.append(s)

    def clear_lines(self, p):
        p.v._import_lines = []

    def extend_lines(self, p, lines):
        p.v._import_lines.extend(list(lines))

    def get_lines(self, p):
        return  p.v._import_lines
        
    def has_lines(self, p):
        return hasattr(p.v, '_import_lines')
        
    def prepend_lines(self, p, lines):
        p.v._import_lines = list(lines) + p.v._import_lines

    def set_lines(self, p, lines):
        p.v._import_lines = list(lines)
    #@+node:ekr.20161108131153.3: *3* i.check & helpers
    def check(self, unused_s, parent):
        '''True if perfect import checks pass.'''
        trace = False and g.unitTesting
        trace_all = True
        trace_lines = True
        trace_status = True
        if g.app.suppressImportChecks:
            if trace and trace_status:
                g.trace('===== skipping all checks', parent.h)
            g.app.suppressImportChecks = False
            return True
        c = self.c
        t1 = time.clock()
        sfn = g.shortFileName(self.root.h)
        s1 = g.toUnicode(self.file_s, self.encoding)
        s2 = self.trial_write()
        lines1, lines2 = g.splitLines(s1), g.splitLines(s2)
        if trace and trace_all:
            g.trace('===== entry')
            self.trace_lines(lines1, lines2, parent)
        if self.ws_error:
            if trace and trace_status: g.trace('===== ws_error: cleaning lws')
            lines1, lines2 = self.strip_lws(lines1), self.strip_lws(lines2)
        else:
            lines1, lines2 = self.clean_blank_lines(lines1), self.clean_blank_lines(lines2)
        # Forgive trailing whitespace problems in the last line:
        if True:
            lines1, lines2 = self.clean_last_lines(lines1), self.clean_last_lines(lines2)
        ok = lines1 == lines2
        if not ok and not self.strict:
            if trace:
                self.show_failure1(lines1, lines2, parent, trace_all, trace_status)
            # Issue an error only if something *other than* lws is amiss.
            lines1, lines2 = self.strip_lws(lines1), self.strip_lws(lines2)
            ok = lines1 == lines2
            if ok and not g.unitTesting:
                print('warning: leading whitespace changed in:', self.root.h)
        if not ok:
            self.show_failure2(lines1, lines2, sfn)
        if trace and trace_all or (not ok and trace_lines):
            self.trace_lines(lines1, lines2, parent)
        # Ensure that the unit tests fail when they should.
        # Unit tests do not generate errors unless the mismatch line does not match.
        if g.app.unitTesting:
            d = g.app.unitTestDict
            d['result'] = ok
            if not ok:
                d['fail'] = g.callers()
                # Used in a unit test.
                c.importCommands.errors += 1
        t2 = time.clock()
        if t2 - t1 > 0.1:
            print('')
            g.trace('Excessive i.check time: %5.2f sec. in %s' % (t2-t1, sfn))
        return ok
    #@+node:ekr.20161108131153.4: *4* i.clean_blank_lines
    def clean_blank_lines(self, lines):
        '''Remove all blanks and tabs in all blank lines.'''
        return [self.lstrip_line(z) if z.isspace() else z for z in lines]
    #@+node:ekr.20161124030004.1: *4* i.clean_last_lines
    def clean_last_lines(self, lines):
        '''Remove blank lines from the end of lines.'''
        while lines and lines[-1].isspace():
            lines.pop()
        return lines
    #@+node:ekr.20161125031613.1: *4* i.show_failure1
    def show_failure1(self, lines1, lines2, parent, trace_all, trace_status):
        '''Print traces when first checks fail.'''
        if trace_status:
            g.trace('===== %s NOT OK cleaning LWS' % self.name)
        if trace_all:
            self.trace_lines(lines1, lines2, parent)
    #@+node:ekr.20161123210716.1: *4* i.show_failure2
    def show_failure2(self, lines1, lines2, sfn):
        '''Print the failing lines.'''
        if not g.unitTesting:
            g.es('@auto failed:', sfn, color='red')
        n1, n2 = len(lines1), len(lines2)
        print('\n===== PERFECT IMPORT FAILED =====', sfn)
        print('len(s1): %s len(s2): %s' % (n1, n2))
        for i in range(min(n1, n2)):
            line1, line2 = lines1[i], lines2[i]
            if line1 != line2:
                 print('first mismatched line: %s' % (i+1))
                 print(repr(line1))
                 print(repr(line2))
                 break
        else:
            print('all common lines match')
    #@+node:ekr.20161108131153.5: *4* i.strip_*
    def lstrip_line(self, s):
        '''Delete leading whitespace, *without* deleting the trailing newline!'''
        # This fixes a major bug in strip_lws.
        assert s, g.callers()
        return '\n' if s.isspace() else s.lstrip()

    def strip_all(self, lines):
        '''Strip blank lines and leading whitespace from all lines of s.'''
        return self.strip_lws(self.strip_blank_lines(lines))

    def strip_blank_lines(self, lines):
        '''Strip all blank lines from s.'''
        return [z for z in lines if not z.isspace()]
        
    def strip_lws(self, lines):
        '''Strip leading whitespace from all lines.'''
        return [self.lstrip_line(z) for z in lines]
        # This also works, but I prefer the "extra" call to lstrip().
        # return ['\n' if z.isspace() else z.lstrip() for z in lines].

        
    #@+node:ekr.20161123210335.1: *4* i.trace_lines
    def trace_lines(self, lines1, lines2, parent):
        '''Show both s1 and s2.'''
        print('===== s1: %s' % parent.h)
        for i, s in enumerate(lines1):
            print('%3s %r' % (i+1, s))
        print('===== s2')
        for i, s in enumerate(lines2):
            print('%3s %r' % (i+1, s))
    #@+node:ekr.20161108131153.6: *4* i.trial_write
    def trial_write(self):
        '''Return the trial write for self.root.'''
        at = self.c.atFileCommands
        if self.gen_refs:
            # Alas, the *actual* @auto write code refuses to write section references!!
            at.write(self.root,
                    nosentinels=True,           # was False,
                    perfectImportFlag=False,    # was True,
                    scriptWrite=True,           # was False,
                    thinFile=True,
                    toString=True,
                )
        else:
            at.writeOneAtAutoNode(
                self.root,
                toString=True,
                force=True,
                trialWrite=True,
            )
        return g.toUnicode(at.stringOutput, self.encoding)
    #@+node:ekr.20161108131153.7: *3* i.Overrides
    # These can be overridden in subclasses.
    #@+node:ekr.20161108131153.8: *4* i.adjust_parent
    def adjust_parent(self, parent, headline):
        '''Return the effective parent.

        This is overridden by the RstScanner class.'''
        return parent
    #@+node:ekr.20161108131153.9: *4* i.clean_headline
    def clean_headline(self, s):
        '''
        Return the cleaned version headline s.
        Will typically be overridden in subclasses.
        '''
        return s.strip()
    #@+node:ekr.20161110173058.1: *4* i.clean_nodes
    def clean_nodes(self, parent):
        '''
        Clean all nodes in parent's tree.
        Subclasses override this as desired.
        See perl_i.clean_nodes for an examplle.
        '''
        pass
    #@+node:ekr.20161120022121.1: *3* i.Scanning & scan tables
    #@+node:ekr.20161128190217.1: *4* i. to be retired
    #@+node:ekr.20161113135037.1: *5* i.get_table
    #@@nobeautify
    cached_scan_tables = {}

    def get_table(self, context):
        '''
        Return the state table for the given context.
        
        This method handles caching.  x.get_new_table returns the actual table.
        '''
        key = '%s.%s' % (self.name, context)
            # Bug fix: must keep tables separate.
        table = self.cached_scan_tables.get(key)
        if table:
            return table
        else:
            table = self.get_new_dict(context)
            self.cached_scan_tables[key] = table
            return table
    #@+node:ekr.20161113052225.1: *5* i.scan_table
    def scan_table(self, context, i, s, table):
        '''
        i.scan_table: Scan at position i of s with the give context and table.
        Return the 6-tuple: (new_context, i, delta_c, delta_p, delta_s, bs_nl)
        '''
        trace = False and g.unitTesting
        if trace: g.trace('='*20, repr(context))
        # kind,   pattern, out-ctx,     in-ctx,     delta{}, delta(), delta[]
        for kind, pattern, out_context, in_context, delta_c, delta_p, delta_s in table:
            # pattern may be None in the general table,
            # because not all languages have all comment delims.
            if pattern and self.match(s, i, pattern):
                if not kind.startswith('end'):
                    assert kind in ('all', 'len', 'len+1'), kind
                # Backslash patterns must match in all contexts!
                if pattern.startswith('\\'):
                    ok = True
                    if trace: g.trace(
                        '----- context: %r in_context: %r out_context: %r' % (
                            context, in_context, out_context))
                    new_context = out_context
                elif context == '':
                    ok = True
                    new_context = out_context
                elif kind.startswith('end'):
                    tail = kind[3:]
                    ok = tail and context == tail
                    new_context = in_context
                else:
                    ok = context == pattern
                    new_context = in_context
                if ok:
                    assert new_context is not None, (pattern, repr(s))
                    if trace: g.trace(
                        '   MATCH: i: %s ch: %4r kind: %5s pattern: %5r '
                        'context: %5r new_context: %5r line: %r' % (
                        i, s[i], kind, pattern, context, new_context, s))
                    if kind == 'all':
                        i = len(s)
                    elif kind == 'len+1':
                        i += (len(pattern) + 1)
                    else:
                        assert kind.startswith('end') or kind == 'len', (kind, self.name)
                        i += len(pattern)
                    bs_nl = pattern == '\\\n'
                    return new_context, i, delta_c, delta_p, delta_s, bs_nl
        # No match: stay in present state. All deltas are zero.
        if trace: g.trace('NO MATCH: i: %s ch: %4r context: %5r line: %r' % (i, s[i], context, s))
        return context, i+1, 0, 0, 0, False
    #@+node:ekr.20161128025508.1: *4* i.get_new_dict
    #@@nobeautify

    def get_new_dict(self, context):
        '''
        Return a *general* state dictionary for the given context.
        Subclasses may override...
        '''
        trace = False and g.unitTesting
        comment, block1, block2 = self.single_comment, self.block1, self.block2
        
        def add_key(d, key, data):
            aList = d.get(key,[])
            aList.append(data)
            d[key] = aList

        if context:
            d = {
                # key    kind   pattern  ends?
                '\\':   [('len+1', '\\', None),],
                '"':    [('len', '"',    context == '"'),],
                "'":    [('len', "'",    context == "'"),],
            }
            if block1 and block2:
                add_key(d, block2[0], ('len', block1, True))
        else:
            # Not in any context.
            d = {
                # key    kind pattern new-ctx  deltas
                '\\':[('len+1', '\\', context, None),],
                '"':    [('len', '"', '"',     None),],
                "'":    [('len', "'", "'",     None),],
                '{':    [('len', '{', context, (1,0,0)),],
                '}':    [('len', '}', context, (-1,0,0)),],
                '(':    [('len', '(', context, (0,1,0)),],
                ')':    [('len', ')', context, (0,-1,0)),],
                '[':    [('len', '[', context, (0,0,1)),],
                ']':    [('len', ']', context, (0,0,-1)),],
            }
            if comment:
                add_key(d, comment[0], ('all', comment, '', None))
            if block1 and block2:
                add_key(d, block1[0], ('len', block1, block1, None))
        if trace: g.trace('created %s dict for %r state ' % (self.name, context))
        return d
    #@+node:ekr.20161128025444.1: *4* i.scan_dict
    def scan_dict(self, context, i, s, d):
        '''
        i.scan_dict: Scan at position i of s with the give context and dict.
        Return the 6-tuple: (new_context, i, delta_c, delta_p, delta_s, bs_nl)
        '''
        trace = False and g.unitTesting
        trace_fail = False
        if trace and trace_fail: g.trace('='*20, repr(context))
        found = False
        delta_c = delta_p = delta_s = 0
        ch = s[i] # For traces.
        aList = d.get(ch)
        if aList and context:
            # In context.
            for data in aList:
                kind, pattern, ends = data
                if self.match(s, i, pattern):
                    if ends == None:
                        found = True
                        new_context = context
                        break
                    elif ends:
                        found = True
                        new_context = ''
                        break
                    else:
                        pass # Ignore this match.
        elif aList:
            # Not in context.
            for data in aList:
                kind, pattern, new_context, deltas = data
                # try:
                    # kind, pattern, new_context, deltas = data
                # except ValueError:
                    # g.trace(data)
                    # break
                if self.match(s, i, pattern):
                    found = True
                    if deltas:
                        delta_c, delta_p, delta_s = deltas
                    break
        if found:
            if kind == 'all':
                i = len(s)
            elif kind == 'len+1':
                i += (len(pattern) + 1)
            else:
                assert kind == 'len', (kind, self.name)
                i += len(pattern)
            bs_nl = pattern == '\\\n'
            if trace:
                g.trace(
                    '   MATCH: i: %s ch: %r kind: %r pattern: %r '
                    'context: %r new_context: %r line: %r' % (
                        i, ch, kind, pattern, context, new_context, s))
                g.trace('deltas', delta_c, delta_p, delta_s)
                g.trace('data', data)
            return new_context, i, delta_c, delta_p, delta_s, bs_nl
        else:
            # No match: stay in present state. All deltas are zero.
            new_context = context
            if trace and trace_fail: g.trace(
                'NO MATCH: i: %s ch: %r context: %r line: %r' % (
                    i, ch, context, s))
        return new_context, i+1, 0, 0, 0, False
    #@+node:ekr.20161114024119.1: *4* i.test_scan_state
    def test_scan_state(self, tests, State):
        '''
        Test x.scan_line or i.scan_line.

        `tests` is a list of g.Bunches with 'line' and 'ctx' fields.
        
        A typical @command test:
            
            if c.isChanged(): c.save()
            < < imp.reload importers.linescanner and importers.python > >
            importer = py.Py_Importer(c.importCommands, atAuto=True)
            importer.test_scan_state(tests, Python_ScanState)
        '''
        trace = False and g.unitTesting
        assert self.single_comment == '#', self.single_comment
        trace_contexts = True
        trace_states = True
        table = self.get_table(context='')
        contexts = self.all_contexts(table)
        if trace and trace_contexts:
            print('\ncontexts:'+' '.join([repr(z) for z in contexts]))
        for bunch in tests:
            assert bunch.line is not None
            line = bunch.line
            ctx = getattr(bunch, 'ctx', None)
            if trace: g.trace('===== ctx: %r line: %r' % (ctx, line))
            if ctx: # Test one transition.
                ctx_in, ctx_out = ctx
                prev_state =  State()
                prev_state.context = ctx_in
                new_state = self.scan_line(line, prev_state)
                new_context = new_state.context
                if trace and trace_states: g.trace(
                    '\nprev: %s\n new: %s' % (prev_state, new_state))
                assert new_context == ctx_out, (
                    'FAIL1:\nline: %r\ncontext: %r new_context: %r ctx_out: %r\n%s\n%s' % (
                        line, ctx_in, new_context, ctx_out, prev_state, new_state))
            else: # Test all transitions.
                for context in contexts:
                    prev_state =  State()
                    prev_state.context = context
                    new_state = self.scan_line(line, prev_state)
                    if trace and trace_states: g.trace(
                        '\nprev: %s\n new: %s' % (prev_state, new_state))
                    assert new_state.context == context, (
                        'FAIL2:\nline: %r\ncontext: %r new_context: %r\n%s\n%s' % (
                            line, context, new_state.context, prev_state, new_state))
    #@+node:ekr.20161108170435.1: *4* i.scan_line
    def scan_line(self, s, prev_state):
        '''
        A generalized scan-line method.
        
        SCAN STATE PROTOCOL:
        
        The Importer class should have a state_class ivar that references a
        **state class**. This class probably should *not* be subclass of the
        ScanState class, but it should observe the following protocol:
        
        1. The state class's ctor must have the following signature:
            
            def __init__(self, d)
            
        2. The state class must have an update method.
        '''
        trace = False and g.unitTesting
        # This dict allows new data to be added without changing ScanState signatures.
        d = {
            'indent': self.get_int_lws(s),
            'is_ws_line': self.is_ws_line(s),
            'prev':prev_state,
            's':s,
        }
        new_state = self.state_class(d)
        i = 0
        while i < len(s):
            progress = i
            context = new_state.context
            table = self.get_table(context)
            data = self.scan_dict(context, i, s, table)
            i = new_state.update(data)
            assert progress < i
        if trace: g.trace('\n\n%r\n\n%s\n' % (s, new_state))
        return new_state
    #@+node:ekr.20161108165530.1: *3* i.Top level
    #@+node:ekr.20161111024447.1: *4* i.generate_nodes & helpers
    def generate_nodes(self, s, parent):
        '''
        A three-stage pipeline to generate all imported nodes.
        '''
        # Stage 1: generate nodes.
        # After this stage, the p.v._import_lines list contains p's future body text.
        self.gen_lines(s, parent)
        #
        # Optional Stage 2, consisting of zero or more sub-stages.
        # Subclasses may freely override this method, **provided**
        # that all substages use the API for setting body text.
        # Changing p.b directly will cause asserts to fail in i.finish(). 
        self.post_pass(parent)
        #
        # Stage 3: Put directives in the root node and set p.b for all nodes.
        #
        # Subclasses should never need to override this stage.
        self.finish(parent)
    #@+node:ekr.20161108160409.1: *5* Stage 1: i.gen_lines & helpers
    def gen_lines(self, s, parent):
        '''
        Non-recursively parse all lines of s into parent, creating descendant
        nodes as needed.
        '''
        trace = False and g.unitTesting
        tail_p = None
        prev_state = self.state_class()
        target = Target(parent, prev_state)
        stack = [target, target]
        self.inject_lines_ivar(parent)
        for line in g.splitLines(s):
            new_state = self.scan_line(line, prev_state)
            top = stack[-1]
            if trace: self.trace_status(line, new_state, prev_state, stack, top)
            if self.is_ws_line(line):
                p = tail_p or top.p
                self.add_line(p, line)
            elif self.starts_block(line, new_state, prev_state):
                tail_p = None
                self.start_new_block(line, new_state, prev_state, stack)
            elif self.ends_block(line, new_state, prev_state, stack):
                tail_p = self.end_block(line, new_state, stack)
            else:
                p = tail_p or top.p
                self.add_line(p, line)
            prev_state = new_state
    #@+node:ekr.20161127102339.1: *6* i.ends_block
    def ends_block(self, line, new_state, prev_state, stack):
        '''True if line does not end the block.'''
        # Comparing new_state against prev_state does not work for python.
        top = stack[-1]
        return new_state.level() < top.state.level()
    #@+node:ekr.20161119130337.1: *6* i.cut_stack
    def cut_stack(self, new_state, stack):
        '''Cut back the stack until stack[-1] matches new_state.'''
        trace = False and g.unitTesting
        if trace:
            g.trace(new_state)
            g.printList(stack)
        assert len(stack) > 1 # Fail on entry.
        while stack:
            top_state = stack[-1].state
            if new_state.level() < top_state.level():
                if trace: g.trace('new_state < top_state', top_state)
                assert len(stack) > 1, stack # <
                stack.pop()
            elif top_state.level() == new_state.level():
                if trace: g.trace('new_state == top_state', top_state)
                assert len(stack) > 1, stack # ==
                # This is the only difference between i.cut_stack and python/cs.cut_stack
                # stack.pop()
                break
            else:
                # This happens often in valid Python programs.
                if trace: g.trace('new_state > top_state', top_state)
                break
        # Restore the guard entry if necessary.
        if len(stack) == 1:
            if trace: g.trace('RECOPY:', stack)
            stack.append(stack[-1])
        assert len(stack) > 1 # Fail on exit.
        if trace: g.trace('new target.p:', stack[-1].p.h)
    #@+node:ekr.20161108160409.3: *6* i.end_block
    def end_block(self, line, new_state, stack):
        # The block is ending. Add tail lines until the start of the next block.
        p = stack[-1].p
        self.add_line(p, line)
        self.cut_stack(new_state, stack)
        tail_p = None if self.gen_refs else p
        return tail_p
    #@+node:ekr.20161110041440.1: *6* i.inject_lines_ivar
    def inject_lines_ivar(self, p):
        '''Inject _import_lines into p.v.'''
        assert not p.v._bodyString, repr(p.v._bodyString)
        p.v._import_lines = []
    #@+node:ekr.20161108160409.6: *6* i.start_new_block
    def start_new_block(self, line, new_state, prev_state, stack):
        '''Create a child node and update the stack.'''
        trace = False and g.unitTesting
        if hasattr(new_state, 'in_context'):
            assert not new_state.in_context(), ('start_new_block', new_state)
        target=stack[-1]
        # Insert the reference in *this* node.
        h = self.gen_ref(line, target.p, target)
        # Create a new child and associated target.
        child = self.create_child_node(target.p, line, h)
        stack.append(Target(child, new_state))
        if trace:
            g.trace('=====', repr(line))
            g.printList(stack)
    #@+node:ekr.20161119124217.1: *6* i.starts_block
    def starts_block(self, line, new_state, prev_state):
        '''True if the new state starts a block.'''
        return new_state.level() > prev_state.level()
    #@+node:ekr.20161119162451.1: *6* i.trace_status
    def trace_status(self, line, new_state, prev_state, stack, top):
        '''Print everything important in the i.gen_lines loop.'''
        print('')
        try:
            g.trace('===== %r' % line)
        except Exception:
            g.trace('     top.p: %s' % g.toEncodedString(top.p.h))
        print('len(stack): %s' % len(stack))
        print(' new_state: %s' % new_state)
        print('prev_state: %s' % prev_state)
        # print(' top.state: %s' % top.state)
        g.printList(stack)
    #@+node:ekr.20161108160409.7: *6* i.create_child_node
    def create_child_node(self, parent, body, headline):
        '''Create a child node of parent.'''
        child = parent.insertAsLastChild()
        self.inject_lines_ivar(child)
        if body:
            self.add_line(child, body)
        assert g.isString(headline), repr(headline)
        child.h = headline.strip()
        return child
    #@+node:ekr.20161108160409.8: *6* i.gen_ref
    def gen_ref(self, line, parent, target):
        '''
        Generate the ref line and a flag telling this method whether a previous
        #@+others
        #@-others
        '''
        trace = False and g.unitTesting
        indent_ws = self.get_str_lws(line)
        h = self.clean_headline(line) 
        if self.is_rst and not self.atAuto:
            return None, None
        elif self.gen_refs:
            headline = g.angleBrackets(' %s ' % h)
            ref = '%s%s\n' % (
                indent_ws,
                g.angleBrackets(' %s ' % h))
        else:
            if target.ref_flag:
                ref = None
            else:
                ref = '%s@others\n' % indent_ws
                target.at_others_flag = True
            target.ref_flag = True
                # Don't generate another @others in this target.
            headline = h
        if ref:
            if trace:
                g.trace('%s indent_ws: %r line: %r parent: %s' % (
                '*' * 20, indent_ws, line, parent.h))
                g.printList(parent.v._import_lines)
            self.add_line(parent,ref)
        return headline
    #@+node:ekr.20161108131153.13: *5* Stage 2: i.post_pass & helpers
    def post_pass(self, parent):
        '''
        Optional Stage 2 of the importer pipeline, consisting of zero or more
        substages. Each substage alters nodes in various ways.
        
        Subclasses may freely override this method, **provided** that all
        substages use the API for setting body text. Changing p.b directly will
        cause asserts to fail later in i.finish().
        '''
        # g.trace('='*40)
        self.clean_all_headlines(parent)
        self.clean_all_nodes(parent)
        self.unindent_all_nodes(parent)
        #
        # This sub-pass must follow unindent_all_nodes.
        self.promote_trailing_underindented_lines(parent)
        #
        # This probably should be the last sub-pass.
        self.delete_all_empty_nodes(parent)
        
    #@+node:ekr.20161110125940.1: *6* i.clean_all_headlines
    def clean_all_headlines(self, parent):
        '''
        Clean all headlines in parent's tree by calling the language-specific
        clean_headline method.
        '''
        for p in parent.subtree():
            h = self.clean_headline(p.h)
            if h:
                if h != p.h: p.h = h
            else:
                pass
                # g.trace('empty headline', p, 'parent', parent.h)
    #@+node:ekr.20161110130157.1: *6* i.clean_all_nodes
    def clean_all_nodes(self, parent):
        '''Clean the nodes in parent's tree, in a language-dependent way.'''
        # i.clean_nodes does nothing.
        # Subclasses may override as desired.
        # See perl_i.clean_nodes for an example.
        self.clean_nodes(parent)
    #@+node:ekr.20161110130709.1: *6* i.delete_all_empty_nodes
    def delete_all_empty_nodes(self, parent):
        '''
        Delete nodes consisting of nothing but whitespace.
        Move the whitespace to the preceding node.
        '''
        c = self.c
        aList = []
        for p in parent.subtree():
            back = p.threadBack()
            if back != parent and not p.isCloned():
                lines = self.get_lines(p)
                # Move the whitespace from p to back.
                if all([z.isspace() for z in lines]):
                    self.extend_lines(back, lines)
                    aList.append(p.copy())
        c.deletePositionsInList(aList)
    #@+node:ekr.20161110131509.1: *6* i.promote_trailing_underindented_lines
    def promote_trailing_underindented_lines(self, parent):
        '''
        Promote all trailing underindent lines to the node's parent node,
        deleting one tab's worth of indentation. Typically, this will remove
        the underindent escape.
        '''
        pattern = self.escape_pattern # A compiled regex pattern
        for p in parent.subtree():
            lines = self.get_lines(p)
            tail = []
            while lines:
                line = lines[-1]
                m = pattern.match(line)
                if m:
                    lines.pop()
                    n_str = m.group(1)
                    try:
                        n = int(n_str)
                    except ValueError:
                        break
                    if n == abs(self.tab_width):
                        new_line = line[len(m.group(0)):]
                        tail.append(new_line)
                    else:
                        g.trace('unexpected unindent value', n)
                        break
                else:
                    break
            if tail:
                parent = p.parent()
                if parent.parent() == self.root:
                    parent = parent.parent()
                self.set_lines(p, lines)
                self.extend_lines(parent, reversed(tail))
                
    #@+node:ekr.20161110130337.1: *6* i.unindent_all_nodes
    def unindent_all_nodes(self, parent):
        '''Unindent all nodes in parent's tree.'''
        for p in parent.subtree():
            lines = self.get_lines(p)
            if all([z.isspace() for z in lines]):
                # Somewhat dubious, but i.check covers for us.
                self.clear_lines(p)
            else:
                self.set_lines(p, self.undent(p))
    #@+node:ekr.20161111023249.1: *5* Stage 3: i.finish & helpers
    def finish(self, parent):
        '''
        Stage 3 (the last) stage of the importer pipeline.

        Subclasses should never need to override this method.
        '''
        # Put directives at the end, so as not to interfere with shebang lines, etc.
        self.add_root_directives(parent)
        #
        # Finally, remove all v._import_list temporaries.
        self.finalize_ivars(parent)
    #@+node:ekr.20161108160409.5: *6* i.add_root_directives
    def add_root_directives(self, parent):
        '''Return the proper directives for the root node p.'''
        table = [
            '@language %s\n' % self.language,
            '@tabwidth %d\n' % self.tab_width,
        ]
        if self.parse_body:
            pass
        else:
            self.extend_lines(parent, table)
    #@+node:ekr.20161110042020.1: *6* i.finalize_ivars
    def finalize_ivars(self, parent):
        '''
        Update the body text of all nodes in parent's tree using the injected
        v._import_lines lists.
        '''
        trace = False and g.unitTesting
        for p in parent.self_and_subtree():
            v = p.v
            # Make sure that no code in x.post_pass has mistakenly set p.b.
            assert not v._bodyString, repr(v._bodyString)
            lines = v._import_lines
            if lines:
                if not lines[-1].endswith('\n'):
                    if trace: g.trace('===== add newline', repr(lines[-1]), p.h)
                    lines[-1] += '\n'
            if trace:
                g.trace('=====', repr(p.h))
                self.print_lines(lines)
            v._bodyString = ''.join(lines)
            delattr(v, '_import_lines')
    #@+node:ekr.20161108131153.10: *4* i.run (entry point) & helpers
    def run(self, s, parent, parse_body=False, prepass=False):
        '''The common top-level code for all scanners.'''
        trace = False and g.unitTesting
        if trace: g.trace('='*20, self.name)
        if trace: g.trace('=' * 10, parent.h)
        c = self.c
        if prepass:
            g.trace('(Importer) Can not happen, prepass is True')
            return True, [] # Don't split any nodes.
        self.root = root = parent.copy()
        self.file_s = s
        # Init the error/status info.
        self.errors = 0
        self.parse_body = parse_body
        # Check for intermixed blanks and tabs.
        self.tab_width = c.getTabWidth(p=root)
        ws_ok = self.check_blanks_and_tabs(s) # Only issues warnings.
        # Regularize leading whitespace
        if not ws_ok:
            s = self.regularize_whitespace(s)
        # Generate the nodes, including directives and section references.
        changed = c.isChanged()
        # Completely generate all nodes.
        self.generate_nodes(s, parent)
        # Check the generated nodes.
        # Return True if the result is equivalent to the original file.
        ok = self.errors == 0 and self.check(s, parent)
        g.app.unitTestDict['result'] = ok
        # Insert an @ignore directive if there were any serious problems.
        if not ok:
            self.insert_ignore_directive(parent)
        # It's always useless for an an import to dirty the outline.
        for p in root.self_and_subtree():
            p.clearDirty()
        c.setChanged(changed)
        if trace: g.trace('-' * 10, parent.h)
        return ok
    #@+node:ekr.20161108131153.11: *5* i.check_blanks_and_tabs
    def check_blanks_and_tabs(self, lines):
        '''Check for intermixed blank & tabs.'''
        # Do a quick check for mixed leading tabs/blanks.
        trace = False and not g.unitTesting
        fn = g.shortFileName(self.root.h)
        w = self.tab_width
        blanks = tabs = 0
        for s in g.splitLines(lines):
            lws = self.get_str_lws(s)
            blanks += lws.count(' ')
            tabs += lws.count('\t')
        # Make sure whitespace matches @tabwidth directive.
        if w < 0:
            ok = tabs == 0
            message = 'tabs found with @tabwidth %s in %s' % (w, fn)
        elif w > 0:
            ok = blanks == 0
            message = 'blanks found with @tabwidth %s in %s' % (w, fn)
        if ok:
            ok = blanks == 0 or tabs == 0
            message = 'intermixed blanks and tabs in: %s' % (fn)
        if ok:
            if trace: g.trace('=====', len(lines), blanks, tabs)
        else:
            if g.unitTesting:
                self.report(message)
            else:
                g.es_print(message)
        return ok
    #@+node:ekr.20161108131153.12: *5* i.insert_ignore_directive
    def insert_ignore_directive(self, parent):
        c = self.c
        parent.b = parent.b.rstrip() + '\n@ignore\n'
        if g.unitTesting:
            g.app.unitTestDict['fail'] = g.callers()
        elif parent.isAnyAtFileNode() and not parent.isAtAutoNode():
            g.warning('inserting @ignore')
            c.import_error_nodes.append(parent.h)
    #@+node:ekr.20161108131153.14: *5* i.regularize_whitespace
    def regularize_whitespace(self, s):
        '''
        Regularize leading whitespace in s:
        Convert tabs to blanks or vice versa depending on the @tabwidth in effect.
        '''
        trace = False and not g.unitTesting
        trace_lines = False
        kind = 'tabs' if self.tab_width > 0 else 'blanks'
        kind2 = 'blanks' if self.tab_width > 0 else 'tabs'
        fn = g.shortFileName(self.root.h)
        lines = g.splitLines(s)
        count, result, tab_width = 0, [], self.tab_width
        self.ws_error = False ### 2016/11/23
        if tab_width < 0: # Convert tabs to blanks.
            for n, line in enumerate(lines):
                i, w = g.skip_leading_ws_with_indent(line, 0, tab_width)
                s = g.computeLeadingWhitespace(w, -abs(tab_width)) + line[i:]
                    # Use negative width.
                if s != line:
                    count += 1
                    if trace and trace_lines:
                        g.es_print('%s: %r\n%s: %r' % (n+1, line, n+1, s))
                result.append(s)
        elif tab_width > 0: # Convert blanks to tabs.
            for n, line in enumerate(lines):
                s = g.optimizeLeadingWhitespace(line, abs(tab_width))
                    # Use positive width.
                if s != line:
                    count += 1
                    if trace and trace_lines:
                        g.es_print('%s: %r\n%s: %r' % (n+1, line, n+1, s))
                result.append(s)
        if count:
            self.ws_error = True # A flag to check.
            if not g.unitTesting:
                # g.es_print('Warning: Intermixed tabs and blanks in', fn)
                # g.es_print('Perfect import test will ignoring leading whitespace.')
                g.es_print('changed leading %s to %s in %s line%s in %s' % (
                    kind2, kind, count, g.plural(count), fn))
            if g.unitTesting: # Sets flag for unit tests.
                self.report('changed %s lines' % count) 
        return ''.join(result)
    #@+node:ekr.20161108131153.15: *3* i.Utils
    #@+node:ekr.20161114012522.1: *4* i.all_contexts
    def all_contexts(self, table):
        '''
        Return a list of all contexts contained in the third column of the given table.
        
        This is a support method for unit tests.
        '''
        contexts = set()
        d = table
        for key in d:
            aList = d.get(key)
            for data in aList:
                if len(data) == 4:
                    # It's an out-of-context entry.
                    contexts.add(data[2])
        # Order must not matter, so sorting is ok.
        return sorted(contexts)
    #@+node:ekr.20161108155143.4: *4* i.match
    def match(self, s, i, pattern):
        '''Return True if the pattern matches at s[i:]'''
        return s[i:i+len(pattern)] == pattern
    #@+node:ekr.20161108131153.18: *4* i.Messages
    def error(self, s):
        '''Issue an error and cause a unit test to fail.'''
        trace = False
        self.errors += 1
        self.importCommands.errors += 1
        if trace or not g.unitTesting:
            g.error('Error:', s)
        # if g.unitTesting:
            # if self.errors == 1:
                # g.app.unitTestDict['actualErrorMessage'] = s
            # g.app.unitTestDict['actualErrors'] = self.errors
        # else:
            # g.error('Error:', s)

    def report(self, message):
        if self.strict:
            self.error(message)
        else:
            self.warning(message)

    def warning(self, s):
        if not g.unitTesting:
            g.warning('Warning:', s)
    #@+node:ekr.20161109045619.1: *4* i.print_lines
    def print_lines(self, lines):
        '''Print lines for debugging.'''
        print('[')
        for line in lines:
            print(repr(line))
        print(']')

    print_list = print_lines
    #@+node:ekr.20161125174423.1: *4* i.print_stack
    def print_stack(self, stack):
        '''Print a stack of positions.'''
        g.printList([p.h for p in stack])
    #@+node:ekr.20161108131153.21: *4* i.underindented_comment/line
    def underindented_comment(self, line):
        if self.at_auto_warns_about_leading_whitespace:
            self.warning(
                'underindented python comments.\n' +
                'Extra leading whitespace will be added\n' + line)

    def underindented_line(self, line):
        if self.warn_about_underindented_lines:
            self.error(
                'underindented line.\n'
                'Extra leading whitespace will be added\n' + line)
    #@+node:ekr.20161109045312.1: *3* i.Whitespace
    #@+node:ekr.20161108155143.3: *4* i.get_int_lws
    def get_int_lws(self, s):
        '''Return the the lws (a number) of line s.'''
        # Important: use self.tab_width, *not* c.tab_width.
        return g.computeLeadingWhitespaceWidth(s, self.tab_width)
    #@+node:ekr.20161109053143.1: *4* i.get_leading_indent
    def get_leading_indent(self, lines, i, ignoreComments=True):
        '''
        Return the leading whitespace (an int) of the first significant line.
        Ignore blank and comment lines if ignoreComments is True
        '''
        if ignoreComments:
            while i < len(lines):
                if self.is_ws_line(lines[i]):
                    i += 1
                else:
                    break
        return self.get_int_lws(lines[i]) if i < len(lines) else 0
    #@+node:ekr.20161108131153.17: *4* i.get_str_lws
    def get_str_lws(self, s):
        '''Return the characters of the lws of s.'''
        m = re.match(r'([ \t]*)', s)
        return m.group(0) if m else ''
    #@+node:ekr.20161109052011.1: *4* i.is_ws_line
    def is_ws_line(self, s):
        '''Return True if s is nothing but whitespace and single-line comments.'''
        # g.trace('(Importer)', bool(self.ws_pattern.match(s)), repr(s))
        return bool(self.ws_pattern.match(s))
    #@+node:ekr.20161108131153.19: *4* i.undent & helper
    def undent(self, p):
        '''Remove maximal leading whitespace from the start of all lines.'''
        trace = False and g.unitTesting
        if self.is_rst:
            return p.b # Never unindent rst code.
        lines = self.get_lines(p)
        ws = self.common_lws(lines)
        if trace:
            g.trace('common_lws:', repr(ws))
            print('===== lines...')
            for z in lines:
                print(repr(z))
        result = []
        for s in lines:
            if s.startswith(ws):
                result.append(s[len(ws):])
            elif s.isspace():
                # Never change blank lines.
                result.append(s)
            else:
                # Indicate that the line is underindented.
                result.append("%s%s.%s" % (
                    self.c.atFileCommands.underindentEscapeString,
                    g.computeWidth(ws, self.tab_width),
                    s.lstrip()))
        if trace:
            print('----- result...')
            for z in result:
                print(repr(z))
        return result
    #@+node:ekr.20161108131153.20: *5* i.common_lws
    def common_lws(self, lines):
        '''Return the lws (a string) common to all lines.'''
        trace = False and not g.unitTesting # and self.root.h.endswith('.c')
        if not lines:
            return ''
        lws = self.get_str_lws(lines[0])
        for s in lines:
            if not self.is_ws_line(s):
                lws2 = self.get_str_lws(s)
                if lws2.startswith(lws):
                    pass
                elif lws.startswith(lws2):
                    lws = lws2
                else:
                    lws = '' # Nothing in common.
                    break
        if trace:
            g.trace(repr(lws))
            self.print_lines(lines)
        return lws
    #@+node:ekr.20161109072221.1: *4* i.undent_body_lines & helper
    def undent_body_lines(self, lines, ignoreComments=True):
        '''
        Remove the first line's leading indentation from all lines.
        Return the resulting string.
        '''
        trace = False and not g.unitTesting
        if trace:
            g.trace('='*20)
            self.print_lines(lines)
        s = ''.join(lines)
        if self.is_rst:
            return s # Never unindent rst code.
        # Calculate the amount to be removed from each line.
        undent_val = self.get_leading_indent(lines, 0, ignoreComments=ignoreComments)
        if trace: g.trace(undent_val, repr(lines[0]))
        if undent_val == 0:
            return s
        else:
            result = self.undent_by(s, undent_val)
            if trace:
                g.trace('-'*209)
                self.print_lines(g.splitLines(result))
            return result
    #@+node:ekr.20161108180655.2: *5* i.undent_by
    def undent_by(self, s, undent_val):
        '''
        Remove leading whitespace equivalent to undent_val from each line.
        
        Strict languages: prepend the underindent escape for underindented lines.
        '''
        trace = False and not g.app.unitTesting
        if self.is_rst:
            return s # Never unindent rst code.
        result = []
        for line in g.splitlines(s):
            lws_s = self.get_str_lws(line)
            lws = g.computeWidth(lws_s, self.tab_width)
            # Add underindentEscapeString only for strict languages.
            if self.strict and not line.isspace() and lws < undent_val:
                if trace: g.trace('undent_val: %s, lws: %s, %r' % (
                    undent_val, lws, line))
                # End the underindent count with a period to
                # protect against lines that start with a digit!
                result.append("%s%s.%s" % (
                    self.escape, undent_val-lws, line.lstrip()))
            else:
                if trace: g.trace(undent_val, repr(line))
                s = g.removeLeadingWhitespace(line, undent_val, self.tab_width)
                result.append(s)
        return ''.join(result)
    #@-others
#@+node:ekr.20161108171914.1: ** class ScanState
class ScanState:
    '''
    The base class for classes representing the state of the line-oriented
    scan.
    '''
    
    def __init__(self, d=None):
        '''ScanState ctor.'''
        if d:
            indent = d.get('indent')
            prev = d.get('prev')
            self.indent = indent # NOT prev.indent
            self.bs_nl = prev.bs_nl
            self.context = prev.context
            self.curlies = prev.curlies
            self.parens = prev.parens
            self.squares = prev.squares
        else:
            self.bs_nl = False
            self.context = ''
            self.curlies = self.indent = self.parens = self.squares = 0

    #@+others
    #@+node:ekr.20161118043146.1: *3* ScanState.__repr__
    def __repr__(self):
        '''ScanState.__repr__'''
        return 'ScanState context: %r curlies: %s' % (
            self.context, self.curlies)
    #@+node:ekr.20161119115215.1: *3* ScanState.level
    def level(self):
        '''ScanState.level.'''
        return self.curlies
    #@+node:ekr.20161118043530.1: *3* ScanState.update
    def update(self, data):
        '''
        Update the state using the 6-tuple returned by i.scan_line.
        Return i = data[1]
        '''
        context, i, delta_c, delta_p, delta_s, bs_nl = data
        self.bs_nl = bs_nl
        self.context = context
        self.curlies += delta_c  
        self.parens += delta_p
        self.squares += delta_s
        return i

    #@-others
#@+node:ekr.20161108155158.1: ** class Target
class Target:
    '''
    A class describing a target node p.
    state is used to cut back the stack.
    '''

    def __init__(self, p, state):
        '''Target ctor.'''
        self.at_others_flag = False
            # True: @others has been generated for this target.
        self.p = p
        self.gen_refs = False
            # Can be forced True.
        self.ref_flag = False
            # True: @others or section reference should be generated.
            # It's always True when gen_refs is True.
        self.state = state

    def __repr__(self):
        return 'Target: %s @others: %s refs: %s p: %s' % (
            self.state,
            int(self.at_others_flag),
            int(self.gen_refs),
            g.shortFileName(self.p.h),
        )
#@-others
#@@language python
#@@tabwidth -4
#@@pagewidth 70
#@-leo
