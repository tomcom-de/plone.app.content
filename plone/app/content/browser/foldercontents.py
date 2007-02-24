from Acquisition import Explicit, aq_parent, aq_inner

from zope.component import getMultiAdapter
from zope.interface import implements, providedBy
from zope.app.pagetemplate import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName
from Products.PythonScripts import standard
from Products.Five import BrowserView
from plone.app.content.browser.interfaces import IFolderContentsView

from Products.ATContentTypes.interface import IATTopic

from ZODB.POSException import ConflictError
from Products.CMFCore.utils import getToolByName
from AccessControl import Unauthorized

from OFS.interfaces import IOrderedContainer

import urllib
from plone.app.content.batching import Batch
from kss.core import KSSView

NOT_ADDABLE_TYPES = ('Favorite',)

class FolderContentsView(BrowserView):
    """
    """
    implements(IFolderContentsView)
    
    def test(self, a, b, c):
        """
        """
        if a:
            return b
        return c
        
    def getAllowedTypes(self):
        """
        """
        # taken from plone_sripts/getAddableTypes 
        types =  self.context.sortObjects(self.context.allowedContentTypes())
        return [ctype for ctype in types if ctype.getId() not in
                NOT_ADDABLE_TYPES]

    @property
    def num_types(self):
        """
        """
        return len(self.getAllowedTypes())

    @property
    def exactly_one_type_addable(self):
        """
        """
        return self.num_types == 1    
        
    @property
    def show_select_add_item(self):
        """
        """
        return self.num_types > 1

    @property    
    def id_of_addable_content_type(self):
        """        
        """
        content_types = self.getAllowedTypes()
        return content_types[0].getId()
                            
    def contents_table(self):
        table = FolderContentsTable(self.context, self.request)
        return table.render()



class FolderContentsKSSView(KSSView):
    def select(self):
        table = FolderContentsTable(self.context, self.request)
        return self.replaceTable(table)

    def sort_on(self, sort_on):
        table = FolderContentsTable(self.context, self.request,
                                    contentFilter={'sort_on':sort_on})
        return self.replaceTable(table)

    def replaceTable(self, table):
        core = self.getCommandSet('core')
        core.replaceInnerHTML('#folderlisting-main-viewlet', table.render())
        return self.render()

class FolderContentsTable(object):
    """   
    The foldercontents table renders the table and its actions.
    """                

    def __init__(self, context, request, contentFilter={}):
        self.context = context
        self.request = request
        requestContentFilter = self.request.get("contentFilter", {})
        requestContentFilter.update(contentFilter)
        self.contentFilter = requestContentFilter

        selection = request.get('select')
        if selection == 'screen':
            self.selectcurrentbatch=True
        elif selection == 'all':
            self.selectall = True

    @property
    def url(self):
        return self.context.absolute_url()+'/@@folder_contents'

    render = ViewPageTemplateFile("foldercontents_table.pt")

    # options
    selectcurrentbatch = False
    _select_all = False

    def _get_select_all(self):
        return self._select_all

    def _set_select_all(self, value):
        self._select_all = bool(value)
        if self._select_all:
            self.selectcurrentbatch = True

    selectall = property(_get_select_all, _set_select_all)

    @property
    def show_select_all_items(self):
        return self.selectcurrentbatch and not self.selectall


    def get_icon(self):
        """
        """
        return getattr(self.context, self.context.getIcon(1)).tag(alt = self.context.portal_type)

    def show_sort_column(self):
        """
        """
        return self.orderable and self.editable

    def get_nosort_class(self):
        """
        """
        if self.orderable:
            return "nosort"
        else:
            return ""

    def title(self):
        """
        """
        return self.context.pretty_title_or_id()

    @property
    def selectall_url(self):
        return self.selectnone_url+'&select=all'

    @property
    def selectscreen_url(self):
        return self.selectnone_url+'&select=screen'

    @property
    def selectnone_url(self):
        url = self.context.absolute_url()
        pagenumber = self.request.get('pagenumber', '1')
        return url+'/@@folder_contents?pagenumber=%s'%pagenumber

    def setbuttonclass(self, button):
        if button['id'] == 'paste':
            button['cssclass'] = 'standalone'
        else:
            button['cssclass'] = 'context'
        return button

    def folder_buttons(self):
        context_state = getMultiAdapter((self.context, self.request),
                                        name=u'plone_context_state')
        buttons = []
        button_actions = context_state.actions()['folder_buttons']

        # Do not show buttons if there is no data, unless there is data to be
        # pasted
        if not len(self.batch):
            if self.context.cb_dataValid():
                for button in button_actions:
                    if button['id'] == 'paste':
                        return [self.setbuttonclass(button)]
            else:
                return []

        for button in button_actions:
            # Make proper classes for our buttons
            if button['id'] != 'paste' or self.context.cb_dataValid():
                buttons.append(self.setbuttonclass(button))
        return buttons


    def parent_url(self):
        """
        """
        portal_url = getToolByName(self.context, 'portal_url')
        plone_utils = getToolByName(self.context, 'plone_utils')
        portal_membership = getToolByName(self.context, 'portal_membership')

        obj = self.context

        checkPermission = portal_membership.checkPermission

        # Abort if we are at the root of the portal
        if obj is portal_url.getPortalObject():
            return None

        # Get the parent. If we can't get it (unauthorized), use the portal
        parent = aq_parent(aq_inner(obj))
        
        # # We may get an unauthorized exception if we're not allowed to access#
        # the parent. In this case, return None
        try:
            if getattr(parent, 'getId', None) is None or \
                   parent.getId() == 'talkback':
                # Skip any Z3 views that may be in the acq tree;
                # Skip past the talkback container if that's where we are
                parent = aq_parent(aq_inner(parent))

            if not checkPermission('List folder contents', parent):
                return None
    
            return parent.absolute_url()

        except Unauthorized:
            return None        

    def selected(self, brain):
        if self.selectcurrentbatch:
            return True
        return False

            
    @property
    def batch(self):
        """
        """
        putils = getToolByName(self.context, 'plone_utils')
        plone_view = getMultiAdapter((self.context, self.request), name=u'plone')
        wtool = getToolByName(self.context, "portal_workflow")
        portal_properties = getToolByName(self.context, 'portal_properties')
        site_properties = portal_properties.site_properties
        
        use_view_action = site_properties.getProperty('typesUseViewActionInListings', ())
        browser_default = self.context.browserDefault()
                
        if IATTopic.providedBy(self.context):
            contentsMethod = self.context.queryCatalog
        else:
            contentsMethod = self.context.getFolderContents
        
        b_size = self.request.get("b_size", 100)

        results = list()
        for i, obj in enumerate(contentsMethod(self.contentFilter)):
            if i % 2 == 0:
                table_row_class = "draggable even"
            else:
                table_row_class = "draggable odd"

            if self.selected(obj):
                table_row_class += ' selected'
            
            url = obj.getURL()
            path = obj.getPath or "/".join(obj.getPhysicalPath())
            icon = plone_view.getIcon(obj);
            
            type_class = 'contenttype-' + putils.normalizeString(
                obj.portal_type)

            review_state = obj.review_state or wtool.getInfoFor(
                obj, 'review_state', '')

            state_class = 'state-' + putils.normalizeString(review_state)
            relative_url = obj.getURL(relative=True)
            obj_type = obj.portal_type

            modified = plone_view.toLocalizedTime(
                obj.ModificationDate, long_format=1)
            
            if obj_type in use_view_action:
                view_url = url + '/view'
            elif obj.is_folderish:
                view_url = url + "/folder_contents"              
            else:
                view_url = url

            is_browser_default = len(browser_default[1]) == 1 and (
                obj.id == browser_default[1][0])
                                 
            results.append(dict(
                url = url,
                id  = obj.getId,
                quoted_id = standard.url_quote(obj.getId),
                path = path,
                title_or_id = obj.pretty_title_or_id(),
                description = obj.Description,
                obj_type = obj_type,
                size = obj.getObjSize,
                modified = modified,
                icon = icon.html_tag(),
                type_class = type_class,
                wf_state = review_state,
                state_title = wtool.getTitleForStateOnType(review_state,
                                                           obj_type),
                state_class = state_class,
                is_browser_default = is_browser_default,
                folderish = obj.is_folderish,
                relative_url = relative_url,
                view_url = view_url,
                checked = self.selected(obj) and 'checked' or None,
                table_row_class = table_row_class,
                is_expired = self.context.isExpired(obj),
            ))
        return Batch(
            results, pagenumber=int(self.request.get('pagenumber', 1)))

    @property
    def orderable(self):
        """
        """        
        return IOrderedContainer.providedBy(self.context)
        
    def test(self, a, b, c):
        """
        """
        if a:
            return b
        return c

    @property
    def editable(self):
        """
        """
        context_state = getMultiAdapter((self.context, self.request),
                                        name=u'plone_context_state')
        return context_state.is_editable()
        
    def portal(self):
        """
        """    
        utool = getToolByName(self.context, "portal_url")
        return utool.getPortalObject()