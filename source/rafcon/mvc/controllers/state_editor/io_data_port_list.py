"""
.. module:: io_data_port_list
   :platform: Unix, Windows
   :synopsis: A module that holds the controller to list and edit all input- and output-data-ports of a state.

.. moduleauthor:: Sebastian Brunner


"""

import gtk
import gobject
from gtk import ListStore
from gtk import TreeViewColumn, CellRendererToggle

from rafcon.statemachine.states.library_state import LibraryState

from rafcon.mvc.controllers.utils.tab_key import MoveAndEditWithTabKeyListFeatureController
from rafcon.mvc.controllers.utils.selection import ListViewController
from rafcon.mvc.models.abstract_state import AbstractStateModel

from rafcon.mvc.gui_helper import react_to_event
from rafcon.mvc.utils.comparison import compare_variables
from rafcon.utils import log

logger = log.get_logger(__name__)


class DataPortListController(ListViewController):
    """Controller handling the input and output Data Port List
    """
    NAME_STORAGE_ID = 0
    DATA_TYPE_NAME_STORAGE_ID = 1
    DEFAULT_VALUE_STORAGE_ID = 2
    ID_STORAGE_ID = 3
    USE_RUNTIME_VALUE_STORAGE_ID = 4
    RUNTIME_VALUE_STORAGE_ID = 5
    MODEL_STORAGE_ID = 6

    def __init__(self, model, view, io_type):
        super(DataPortListController, self).__init__(model, view, view.get_top_widget(), self.get_new_list_store(),
                                                     logger)
        self.type = io_type
        self.state_data_port_dict = None

        self.tab_edit_controller = MoveAndEditWithTabKeyListFeatureController(self.tree_view)

        if self.type == "input":
            self.state_data_port_dict = self.model.state.input_data_ports
            self.data_port_model_list = self.model.input_data_ports
        elif self.type == "output":
            self.state_data_port_dict = self.model.state.output_data_ports
            self.data_port_model_list = self.model.output_data_ports

        if self.model.get_sm_m_for_state_m() is not None:
            self.observe_model(self.model.get_sm_m_for_state_m())
        else:
            logger.warning("State model has no state machine model -> state model: {0}".format(self.model))

    @staticmethod
    def get_new_list_store():
        return ListStore(str, str, str, int, bool, str, gobject.TYPE_PYOBJECT)

    def default_value_renderer(self, tree_view_column, cell, model, iter):
        """

        :param tree_view_column: the gtk.TreeViewColumn to be rendered
        :param cell: the current CellRenderer
        :param model: the ListStore or TreeStore that is the model for TreeView
        :param iter: an iterator over the rows of the TreeStore/ListStore Model
        """
        if isinstance(self.model.state, LibraryState):
            use_runtime_value = model.get_value(iter, self.USE_RUNTIME_VALUE_STORAGE_ID)
            if use_runtime_value:
                cell.set_property("editable", True)
                cell.set_property('text', model.get_value(iter, self.RUNTIME_VALUE_STORAGE_ID))
                cell.set_property('foreground', "white")
            else:
                cell.set_property("editable", False)
                cell.set_property('text', model.get_value(iter, self.DEFAULT_VALUE_STORAGE_ID))
                cell.set_property('foreground', "dark grey")

        return

    def register_view(self, view):
        """Called when the View was registered"""
        super(DataPortListController, self).register_view(view)

        view['name_col'].add_attribute(view['name_text'], 'text', self.NAME_STORAGE_ID)
        view['data_type_col'].add_attribute(view['data_type_text'], 'text', self.DATA_TYPE_NAME_STORAGE_ID)
        if not isinstance(self.model.state, LibraryState):
            view['name_text'].set_property("editable", True)
            view['data_type_text'].set_property("editable", True)

        # in the linkage overview the the default value is not shown
        if view['default_value_col'] and view['default_value_text']:
            view['default_value_col'].add_attribute(view['default_value_text'], 'text', self.DEFAULT_VALUE_STORAGE_ID)
            # if not isinstance(self.model.state, LibraryState):
            view['default_value_text'].set_property("editable", True)
            self._apply_value_on_edited_and_focus_out(view['default_value_text'], self.apply_new_data_port_default_value)
            if isinstance(self.model.state, LibraryState):
                view['default_value_col'].set_title("Used value")
            view['default_value_col'].set_cell_data_func(view['default_value_text'], self.default_value_renderer)

        self._apply_value_on_edited_and_focus_out(view['name_text'], self.apply_new_data_port_name)
        self._apply_value_on_edited_and_focus_out(view['data_type_text'], self.apply_new_data_port_type)
        view.get_top_widget().connect('button_press_event', self.mouse_click)
        view.get_top_widget().get_selection().connect('changed', self.selection_changed)

        if isinstance(self.model.state, LibraryState):
            view['use_runtime_value_toggle'] = CellRendererToggle()
            view['use_runtime_value_col'] = TreeViewColumn("Use Runtime Value")
            view.get_top_widget().append_column(view['use_runtime_value_col'])
            view['use_runtime_value_col'].pack_start(view['use_runtime_value_toggle'], True)
            view['use_runtime_value_col'].add_attribute(view['use_runtime_value_toggle'], 'active',
                                                        self.USE_RUNTIME_VALUE_STORAGE_ID)
            view['use_runtime_value_toggle'].set_property("activatable", True)
            view['use_runtime_value_toggle'].connect("toggled", self.on_use_runtime_value_toggled)

        self.tab_edit_controller.register_view()
        self.reload_data_port_list_store()

    def register_adapters(self):
        """Adapters should be registered in this method call"""
        pass

    def register_actions(self, shortcut_manager):
        """Register callback methods for triggered actions

        :param rafcon.mvc.shortcut_manager.ShortcutManager shortcut_manager: Shortcut Manager Object holding mappings
            between shortcuts and actions.
        """
        if not isinstance(self.model.state, LibraryState):
            shortcut_manager.add_callback_for_action("delete", self.remove_port)
            shortcut_manager.add_callback_for_action("add", self.add_port)

    def add_port(self, *event):
        """Callback method for add action
        """
        if react_to_event(self.view, self.view[self.view.top], event) and not isinstance(self.model.state, LibraryState):
            self.on_new_port_button_clicked(None)
            return True

    def remove_port(self, *event):
        """Callback method for remove action
        """
        if react_to_event(self.view, self.view[self.view.top], event) and not isinstance(self.model.state, LibraryState):
            self.on_delete_port_button_clicked(None)
            return True

    def get_state_machine_selection(self):
        # print type(self).__name__, "get state machine selection"
        sm_selection = self.model.get_sm_m_for_state_m().selection
        sm_selected_model_list = None
        if self.type == 'input':
            sm_selected_model_list = sm_selection.input_data_ports
        elif self.type == 'output':
            sm_selected_model_list = sm_selection.output_data_ports
        return sm_selection, sm_selected_model_list

    @ListViewController.observe("selection", after=True)
    def state_machine_selection_changed(self, model, prop_name, info):
        if "{}_data_ports".format(self.type) == info['method_name']:
            self.update_selection_sm_prior()

    @ListViewController.observe("input_data_ports", after=True)
    @ListViewController.observe("output_data_ports", after=True)
    def data_ports_changed(self, model, prop_name, info):
        """Reload list store and reminds selection when the model was changed"""
        if "{}_data_ports".format(self.type) == prop_name and isinstance(model, AbstractStateModel):
            # store port selection
            path_list = None
            if self.view is not None:
                model, path_list = self.tree_view.get_selection().get_selected_rows()
            selected_data_port_ids = [self.list_store[path[0]][self.ID_STORAGE_ID] for path in path_list] if path_list else []
            self.reload_data_port_list_store()
            # recover port selection
            if selected_data_port_ids:
                [self.select_entry(selected_data_port_id, False) for selected_data_port_id in selected_data_port_ids]

    @ListViewController.observe("state", after=True)
    def runtime_values_changed(self, model, prop_name, info):
        """Handle cases for the library runtime values"""
        if ("_{}_runtime_value".format(self.type) in info.method_name or
                info.method_name in ['use_runtime_value_{}_data_ports'.format(self.type),
                                     '{}_data_port_runtime_values'.format(self.type)]) and \
                self.model is model:
            self.data_ports_changed(model, "{}_data_ports".format(self.type), info)

    def on_new_port_button_clicked(self, widget, data=None):
        """Add a new port with default values and select it"""

        if self.type == "input":
            num_data_ports = len(self.model.state.input_data_ports)
        else:
            num_data_ports = len(self.model.state.output_data_ports)
        for run_id in range(num_data_ports + 1, 0, -1):
            new_port_name = self.type + "_{0}".format(run_id)
            try:
                if self.type == "input":
                    data_port_id = self.model.state.add_input_data_port(new_port_name, "int", "0")
                else:
                    data_port_id = self.model.state.add_output_data_port(new_port_name, "int", "0")
                break
            except ValueError as e:
                if run_id == num_data_ports:
                    logger.warn("The {1} data port couldn't be added: {0}".format(e, self.type))
                    return False
        self.select_entry(data_port_id)
        return True

    def on_delete_port_button_clicked(self, widget, data=None):
        """Remove the selected ports and select the next one"""
        path_list = None
        if self.view is not None:
            model, path_list = self.tree_view.get_selection().get_selected_rows()
        old_path = self.get_path()
        data_port_ids = [self.list_store[path][self.ID_STORAGE_ID] for path in path_list] if path_list else []
        if data_port_ids:
            for data_port_id in data_port_ids:
                try:
                    if self.type == "input":
                        self.model.state.remove_input_data_port(data_port_id)
                    else:
                        self.model.state.remove_output_data_port(data_port_id)
                except AttributeError as e:
                    logger.warn("The data port couldn't be removed: {0}".format(e))
                    return False
            if len(self.list_store) > 0:
                self.view[self.view.top].set_cursor(min(old_path[0], len(self.list_store) - 1))
            return True

    def on_use_runtime_value_toggled(self, widget, path):
        """Try to set the use runtime value flag to the newly entered one
        """
        # logger.info("on_use_runtime_value_edited widget: {0} path: {1}".format(widget, path))
        try:
            data_port_id = self.list_store[int(path)][self.ID_STORAGE_ID]
            if self.type == "input":
                current_value = self.model.state.use_runtime_value_input_data_ports[data_port_id]
                self.model.state.set_use_input_runtime_value(data_port_id, not current_value)
            else:
                current_value = self.model.state.use_runtime_value_output_data_ports[data_port_id]
                self.model.state.set_use_output_runtime_value(data_port_id, not current_value)
        except TypeError as e:
            logger.error("Error while trying to change the use_runtime_value flag: {0}".format(e))

    def apply_new_data_port_name(self, path, new_name):
        """Applies the new name of the data port defined by path

        :param str path: The path identifying the edited data port
        :param str new_name: New name
        """
        try:
            data_port_id = self.list_store[path][self.ID_STORAGE_ID]
            if self.state_data_port_dict[data_port_id].name != new_name:
                self.state_data_port_dict[data_port_id].name = new_name
        except (TypeError, ValueError) as e:
            logger.error("Error while trying to change the port name: {0}".format(e))

    def apply_new_data_port_type(self, path, new_data_type_str):
        """Applies the new data type of the data port defined by path

        :param str path: The path identifying the edited data port
        :param str new_data_type_str: New data type as str
        """
        try:
            data_port_id = self.list_store[path][self.ID_STORAGE_ID]
            if self.state_data_port_dict[data_port_id].data_type.__name__ != new_data_type_str:
                self.state_data_port_dict[data_port_id].change_data_type(new_data_type_str)
        except ValueError as e:
            logger.error("Error while changing data type: {0}".format(e))

    def apply_new_data_port_default_value(self, path, new_default_value_str):
        """Applies the new default value of the data port defined by path

        :param str path: The path identifying the edited variable
        :param str new_default_value_str: New default value as string
        """
        try:
            data_port_id = self.list_store[path][self.ID_STORAGE_ID]
            if isinstance(self.model.state, LibraryState):
                # this always have to be true, as the runtime value column can only be edited
                # if the use_runtime_value flag is True
                if self.list_store[path][self.USE_RUNTIME_VALUE_STORAGE_ID]:
                    if self.type == "input":
                        if str(self.model.state.input_data_port_runtime_values[data_port_id]) != new_default_value_str:
                            self.model.state.set_input_runtime_value(data_port_id, new_default_value_str)
                    else:
                        if str(self.model.state.output_data_port_runtime_values[data_port_id]) != new_default_value_str:
                            self.model.state.set_output_runtime_value(data_port_id, new_default_value_str)
            else:
                if str(self.state_data_port_dict[data_port_id].default_value) != new_default_value_str:
                    self.state_data_port_dict[data_port_id].default_value = new_default_value_str
        except (TypeError, AttributeError) as e:
            logger.error("Error while changing default value: {0}".format(e))

    def on_right_click_menu(self):
        logger.debug("do right click menu")

    def reload_data_port_list_store(self):
        """Reloads the input data port list store from the data port models"""

        tmp = self.get_new_list_store()
        for idp_model in self.data_port_model_list:
            data_type = idp_model.data_port.data_type
            # get name of type (e.g. ndarray)
            data_type_name = data_type.__name__
            # get module of type, e.g. numpy
            data_type_module = data_type.__module__
            # if the type is not a builtin type, also show the module
            if data_type_module != '__builtin__':
                data_type_name = data_type_module + '.' + data_type_name
            if idp_model.data_port.default_value is None:
                default_value = "None"
            else:
                default_value = idp_model.data_port.default_value

            if not isinstance(self.model.state, LibraryState):
                tmp.append([idp_model.data_port.name, data_type_name, default_value, idp_model.data_port.data_port_id,
                            None, None, idp_model])
            else:
                if self.type == "input":
                    use_runtime_value = self.model.state.use_runtime_value_input_data_ports[
                        idp_model.data_port.data_port_id]
                    runtime_value = self.model.state.input_data_port_runtime_values[idp_model.data_port.data_port_id]
                else:
                    use_runtime_value = self.model.state.use_runtime_value_output_data_ports[
                        idp_model.data_port.data_port_id]
                    runtime_value = self.model.state.output_data_port_runtime_values[idp_model.data_port.data_port_id]
                tmp.append([idp_model.data_port.name,
                            data_type_name,
                            default_value,
                            idp_model.data_port.data_port_id,
                            use_runtime_value,
                            runtime_value,
                            idp_model,
                            ])

        tms = gtk.TreeModelSort(tmp)
        tms.set_sort_column_id(0, gtk.SORT_ASCENDING)
        tms.set_sort_func(0, compare_variables)
        tms.sort_column_changed()
        tmp = tms
        self.list_store.clear()
        for elem in tmp:
            self.list_store.append(elem)
