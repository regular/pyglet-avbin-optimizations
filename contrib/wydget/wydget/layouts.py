import operator

from wydget import util
from wydget.widgets.label import Label

TOP = 'top'
BOTTOM = 'bottom'
LEFT = 'left'
RIGHT = 'right'
CENTER = 'center'
FILL = 'fill'

class Layout(object):
    '''Absolute positioning layout -- also base class for other layouts.

    Elements in the parent are positioined using absolute coordinates in
    the parent's coordinate space.

    "only_visible" -- limits the layout to only those elements which are
                      is_visible (note NOT isVisible - parent visibility
                      obviously makes no sense in this context)
    '''
    def __init__(self, parent, only_visible=False):
        self.only_visible = only_visible
        self.parent = parent

    def __repr__(self):
        return '<%s %dx%d>'%(self.__class__.__name__, self.width, self.height)

    def layout(self):
        # XXX use signal?
        self.parent.layoutDimensionsChanged(self)

    def __call__(self):
        self.layout()

    def add(self, child):
        '''Generally this is a NOOP for simple layouts.

        We generally only care about "child" when it's a child layout.

        See Grid for where this is actually used.
        '''
        pass

    def get_height(self):
        return max(c.y + c.height for c in self.parent.children
            if not self.only_visible or c.is_visible)
    height = property(get_height)

    def get_width(self):
        return max(c.x + c.width for c in self.parent.children
            if not self.only_visible or c.is_visible)
    width = property(get_width)

    def getChildren(self):
        return [c for c in self.parent.children
            if not self.only_visible or c.is_visible]

    @classmethod
    def fromXML(cls, element, parent):
        '''Create the a layout from the XML element and handle children.
        '''
        kw = loadxml.parseAttributes(parent, element)
        parent.layout = layout = cls(parent, **kw)

        for child in element.getchildren():
            child = loadxml.getConstructor(child.tag)(child, layout.parent)
            layout.add(child)
        layout.layout()

        return layout


class Grid(Layout):
    name = 'grid'

    def __init__(self, parent):
        super(Grid, self).__init__(parent)
        self.rows = []

    def add(self, row):
        self.rows.append(row)
    
    def layout(self):
        # XXX allow varying heights
        ys = self.parent.height // len(self.rows)

        for j, row in enumerate(self.rows):
            # XXX allow varying widths
            # XXX allow column spanning
            # XXX allow row spanning
            xs = self.parent.width // len(row.cells)
            for i, cell in enumerate(row.cells):
                if cell.child is None: continue

                x = i * xs
                if cell.halign == CENTER:
                    x += xs // 2 - cell.child.width // 2
                elif cell.halign == RIGHT:
                    x += xs - cell.child.width

                y = j * ys
                if cell.valign == CENTER:
                    y += ys // 2 - cell.child.height // 2
                elif cell.valign == TOP:
                    y += ys - cell.child.height

                cell.child.x, cell.child.y, cell.child.z = x, y, 0

        super(Grid, self).layout()


class Row(Layout):
    name = 'row'
    def __init__(self, parent):
        super(Row, self).__init__(parent)
        self.cells = []

    def add(self, cell):
        self.cells.append(cell)

    def layout(self):
        pass

class Cell(object):
    name = 'cell'

    def __init__(self, parent, child=None, valign=CENTER, halign=CENTER):
        super(Cell, self).__init__(parent)
        self.child = child
        self.valign = valign
        self.halign = halign

    def layout(self):
        pass

    @classmethod
    def fromXML(cls, element, parent):
        kw = loadxml.parseAttributes(parent, element)
        layout = cls(parent, **kw)

        l = element.getchildren()
        if not l: return

        assert len(l) == 1, '<cell> may only have one (or no) child'

        layout.child = loadxml.getConstructor(l[0].tag)(l[0], parent)

        return layout


class Vertical(Layout):
    name = 'vertical'

    def __init__(self, parent, valign=CENTER, halign=None, padding=0, **kw):
        self.valign = valign
        self.halign = halign
        self.padding = util.parse_value(padding, parent.inner_rect.height)
        super(Vertical, self).__init__(parent, *kw)

    def get_height(self):
        if self.valign == FILL:
            # fill means using the available height
            return self.parent.inner_rect.height
        vis = self.getChildren()
        if not vis: return 0
        return sum(c.height for c in vis) + self.padding * (len(vis)-1)
    height = property(get_height)

    def get_width(self):
        vis = self.getChildren()
        if not vis: return 0
        return max(c.width for c in vis)
    width = property(get_width)

    def layout(self):
        # give the parent a chance to resize before we layout
        self.parent.layoutDimensionsChanged(self)

        # now get the area available for our layout
        rect = self.parent.inner_rect

        h = self.height

        vis = self.getChildren()

        if self.valign == TOP:
            y = rect.height
        elif self.valign == CENTER:
            y = rect.height//2 + h//2
        elif self.valign == BOTTOM:
            y = h
        elif self.valign == FILL:
            if len(vis) == 1:
                fill_padding = 0
            else:
                h = sum(c.height for c in vis)
                fill_padding = (rect.height - h)/float(len(vis)-1)
            y = float(rect.height)

        for c in vis:
            if self.halign == LEFT:
                c.x = 0
            elif self.halign == CENTER:
                c.x = rect.width//2 - c.width//2
            elif self.halign == RIGHT:
                c.x = rect.width - c.width

            y -= c.height
            c.y = int(y)
            if self.valign == FILL:
                y -= fill_padding
            else:
                y -= self.padding

        super(Vertical, self).layout()

class Horizontal(Layout):
    name = 'horizontal'

    def __init__(self, parent, halign=CENTER, valign=None, padding=0,
            wrap=None, **kw):
        self.halign = halign
        self.valign = valign
        self.wrap = util.parse_value(wrap, parent.inner_rect.width)
        if wrap and valign is None:
            # we need to align somewhere to wrap
            self.valign = self.BOTTOM
        self.padding = util.parse_value(padding, parent.inner_rect.width)
        super(Horizontal, self).__init__(parent, **kw)

    def get_width(self):
        pw = self.parent.inner_rect.width
        if self.halign == FILL:
            # fill means using the available width
            return pw
        vis = self.getChildren()
        if not vis: return 0
        if self.wrap:
            if self.parent.width_spec:
                # parent width or widest child if wider than parent
                return max(self.wrap, max(c.width for c in vis))
            else:
                # width of widest row
                return max(sum(c.width for c in row) +
                    self.padding * (len(row)-1)
                        for row in self.determineRows())
        return sum(c.width for c in vis) + self.padding * (len(vis)-1)
    width = property(get_width)

    def get_height(self):
        vis = self.getChildren()
        if not vis: return 0
        if self.wrap:
            rows = self.determineRows()
            return sum(max(c.height for c in row) for row in rows) + \
                self.padding * (len(rows)-1)
        return max(c.height for c in vis)
    height = property(get_height)

    def determineRows(self):
        rows = [[]]
        rw = 0
        for c in self.getChildren():
            if self.wrap and rw and rw + c.width > self.wrap:
                rw = 0
                rows.append([])
            row = rows[-1]
            row.append(c)
            rw += c.width
        if not rows[-1]: rows.pop()
        return rows

    def layout(self):
        # give the parent a chance to resize before we layout
        self.parent.layoutDimensionsChanged(self)

        # now get the area available for our layout
        rect = self.parent.inner_rect

        # All very simplistic, assumes all children in a row are the same
        # height. Start y coords out at top of parent.
        if self.valign == BOTTOM:
            y = self.height
        elif self.valign == CENTER:
            y = rect.height//2 - self.height//2 + self.height
        elif self.valign == TOP:
            y = rect.height

        fill_padding = self.padding
        for row in self.determineRows():
            if self.valign is not None:
                y -= max(child.height for child in row)

            # width of this row
            if self.halign == FILL:
                w = rect.width
            else:
                w = sum(c.width for c in row) + self.padding * (len(row)-1)

            # horizontal align for this row
            x = 0
            if self.halign == RIGHT:
                x = int(rect.width - w)
            elif self.halign == CENTER:
                x = rect.width//2 - w//2
            elif self.halign == FILL:
                if len(row) == 1:
                    fill_padding = 0
                else:
                    w = sum(c.width for c in row)
                    fill_padding = (rect.width - w)/float(len(row)-1)

            for child in row:
                child.x = x
                x += int(child.width + fill_padding)
                if self.valign is not None:
                    child.y = y

            if self.wrap:
                y -= self.padding

        super(Horizontal, self).layout()


class Columns(Layout):
    '''A simple table layout that sets column widths in child rows to fit
    all child data.

    Note that this layout ignores *cell* visibility but honors *row*
    visibility for layout purposes.
    '''
    name = 'columns'

    # XXX column alignments
    def __init__(self, parent, colpad=0, rowpad=0, **kw):
        self.colpad = util.parse_value(colpad, 0)
        self.rowpad = util.parse_value(rowpad, 0)
        super(Columns, self).__init__(parent, **kw)

    def columnWidths(self):
        columns = []
        children = self.getChildren()
        N = len(children[0].children)
        for i in range(N):
            w = []
            for row in children:
                pad = i < N-1 and self.colpad or 0
                col = row.children[i]
                w.append(col.width + col.padding * 2 + pad)
            columns.append(max(w))
        return columns

    def get_width(self):
        return sum(self.columnWidths())
    width = property(get_width)

    def get_height(self):
        children = self.getChildren()
        h = sum(max(e.height for e in c.children) + c.padding * 2
            for c in children)
        return h + (len(children)-1) * self.rowpad
    height = property(get_height)

    def layout(self):
        # give the parent a chance to resize before we layout
        self.parent.layoutDimensionsChanged(self)

        children = self.getChildren()

        # determine column widths
        columns = self.columnWidths()

        # right, now position everything
        y = self.height
        for row in children:
            y -= row.height
            row.y = y
            x = 0
            for i, col in enumerate(row.children):
                col.x = x
                x += columns[i]
            row.layout()
            y -= self.rowpad

        super(Columns, self).layout()

class Form(Layout):
    name = 'form'

    def __init__(self, parent, valign=TOP, label_width=None, padding=4,
            **kw):
        self.valign = valign
        if label_width is None:
            label_width = parent.width * .25
        self.label_width = label_width
        self.padding = padding
        pw = parent.inner_rect.width
        self.element_width = pw - (self.label_width + self.padding)
        self.elements = []
        super(Form, self).__init__(parent, **kw)

    def get_width(self):
        return self.parent.width
    width = property(get_width)

    def get_height(self):
        l = [c.height for c in self.elements
            if not self.only_visible or c.is_visible]
        return sum(l) + self.padding * (len(l)-1)
    height = property(get_height)

    def addElement(self, label, element, expand_element=True,
            halign='right', **kw):
        self.elements.append(element)
        if expand_element:
            element.width = self.element_width
        # XXX alignment
        if label:
            element._label = Label(self.parent, label, width=self.label_width,
                halign=halign, **kw)
        else:
            element._label = None

    def layout(self):
        # give the parent a chance to resize before we layout
        self.parent.layoutDimensionsChanged(self)

        # now get the area available for our layout
        rect = self.parent.inner_rect

        h = self.height

        vis = [c for c in self.elements if c.is_visible]

        if self.valign == TOP:
            y = rect.height
        elif self.valign == CENTER:
            y = rect.height//2 + h//2
        elif self.valign == BOTTOM:
            y = h

        for element in vis:
            element.x = self.label_width + self.padding
            y -= element.height
            element.y = y
            if element._label: element._label.y = y
            y -= self.padding

        super(Form, self).layout()


import loadxml
for klass in [Grid, Row, Cell, Vertical, Horizontal, Columns]:
    loadxml.xml_registry[klass.name] = klass

