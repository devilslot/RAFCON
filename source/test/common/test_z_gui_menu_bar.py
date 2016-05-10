import sys
import logging
import gtk
import threading
import os
from os.path import dirname, join

# general tool elements
from rafcon.utils import log

# core elements
import rafcon.statemachine.config
from rafcon.statemachine.states.hierarchy_state import HierarchyState
from rafcon.statemachine.states.execution_state import ExecutionState
from rafcon.statemachine.states.library_state import LibraryState
from rafcon.statemachine.state_machine import StateMachine

# mvc elements
from rafcon.mvc.controllers.main_window import MainWindowController
from rafcon.mvc.views.graphical_editor import GraphicalEditor as OpenGLEditor
from rafcon.mvc.mygaphas.view import ExtendedGtkView as GaphasEditor
from rafcon.mvc.views.main_window import MainWindowView

import rafcon.mvc.statemachine_helper as statemachine_helper

# singleton elements
import rafcon.mvc.singleton
import rafcon.statemachine.singleton
import rafcon.mvc.config as gui_config

# test environment elements
import testing_utils
from testing_utils import call_gui_callback
import pytest


def setup_module(module):
    # set the test_libraries path temporarily to the correct value
    testing_utils.remove_all_libraries()
    library_paths = rafcon.statemachine.config.global_config.get_config_value("LIBRARY_PATHS")
    library_paths["ros"] = rafcon.__path__[0] + "/../test_scripts/ros_libraries"
    library_paths["turtle_libraries"] = rafcon.__path__[0] + "/../test_scripts/turtle_libraries"
    library_paths["generic"] = rafcon.__path__[0] + "/../libraries/generic"


def wait_for_gui():
    while gtk.events_pending():
        gtk.main_iteration(False)


def create_models(*args, **kargs):
    logger = log.get_logger(__name__)
    logger.setLevel(logging.DEBUG)
    for handler in logging.getLogger('gtkmvc').handlers:
        logging.getLogger('gtkmvc').removeHandler(handler)
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(logging.Formatter("%(asctime)s: %(levelname)-8s - %(name)s:  %(message)s"))
    stdout.setLevel(logging.DEBUG)
    logging.getLogger('gtkmvc').addHandler(stdout)
    logging.getLogger('statemachine.state').setLevel(logging.DEBUG)
    logging.getLogger('controllers.state_properties').setLevel(logging.DEBUG)

    state1 = ExecutionState('State1')
    state2 = ExecutionState('State2')
    state4 = ExecutionState('Nested')
    output_state4 = state4.add_output_data_port("out", "int")
    state5 = ExecutionState('Nested2')
    input_state5 = state5.add_input_data_port("in", "int", 0)
    state3 = HierarchyState(name='State3')
    state3.add_state(state4)
    state3.add_state(state5)
    state3.set_start_state(state4)
    state3.add_scoped_variable("share", "int", 3)
    state3.add_transition(state4.state_id, 0, state5.state_id, None)
    state3.add_transition(state5.state_id, 0, state3.state_id, 0)
    state3.add_data_flow(state4.state_id, output_state4, state5.state_id, input_state5)

    ctr_state = HierarchyState(name="Container")
    ctr_state.add_state(state1)
    ctr_state.add_state(state2)
    ctr_state.add_state(state3)
    ctr_state.set_start_state(state1)
    ctr_state.add_transition(state1.state_id, 0, state2.state_id, None)
    ctr_state.add_transition(state2.state_id, 0, state3.state_id, None)
    ctr_state.add_transition(state3.state_id, 0, ctr_state.state_id, 0)
    ctr_state.name = "Container"

    return logger, ctr_state


def focus_graphical_editor_in_page(page):
    graphical_controller = page.children()[0]
    if not isinstance(graphical_controller, (OpenGLEditor, GaphasEditor)):
        graphical_controller = graphical_controller.children()[0]
    graphical_controller.grab_focus()


def select_and_paste_state(statemachine_model, source_state_model, target_state_model, menu_bar_ctrl, operation,
                           main_window_controller, page):
    """Select a particular state and perform an operation on it (Copy or Cut) and paste it somewhere else. At the end,
    verify that the operation was completed successfully.

    :param statemachine_model: The statemachine model where the operation will be conducted
    :param source_state_model: The state model, on which the operation will be performed
    :param target_state_model: The state model, where the source state will be pasted
    :param menu_bar_ctrl: The menu_bar controller, through which copy, cut & paste actions are triggered
    :param operation: String indicating the operation to be performed (Copy or Cut)
    :param main_window_controller: The MainWindow Controller
    :param page: The notebook page of the corresponding statemachine in the statemachines editor
    :return: The target state model, and the child state count before pasting
    """
    print "\n\n %s \n\n" % source_state_model.state.name
    call_gui_callback(statemachine_model.selection.set, [source_state_model])
    call_gui_callback(getattr(menu_bar_ctrl, 'on_{}_selection_activate'.format(operation)), None, None)
    print "\n\n %s \n\n" % target_state_model.state.name
    call_gui_callback(statemachine_model.selection.set, [target_state_model])
    old_child_state_count = len(target_state_model.state.states)
    main_window_controller.view['main_window'].grab_focus()
    focus_graphical_editor_in_page(page)
    call_gui_callback(menu_bar_ctrl.on_paste_clipboard_activate, None, None)
    wait_for_gui()
    print target_state_model.state.states.keys()
    assert len(target_state_model.state.states) == old_child_state_count + 1
    return target_state_model, old_child_state_count


def copy_and_paste_state_into_itself(sm_m, state_m_to_copy, page, menu_bar_ctrl):
    call_gui_callback(sm_m.selection.set, [state_m_to_copy])
    focus_graphical_editor_in_page(page)
    call_gui_callback(menu_bar_ctrl.on_copy_selection_activate, None, None)
    old_child_state_count = len(state_m_to_copy.state.states)
    call_gui_callback(sm_m.selection.set, [state_m_to_copy])
    focus_graphical_editor_in_page(page)
    call_gui_callback(menu_bar_ctrl.on_paste_clipboard_activate, None, None)
    assert len(state_m_to_copy.state.states) == old_child_state_count + 1


@log.log_exceptions(None, gtk_quit=True)
def trigger_gui_signals(*args):
    """The function triggers and test basic functions of the menu bar.

    At the moment those functions are tested:
    - New State Machine
    - Open State Machine
    - Copy State/HierarchyState -> via GraphicalEditor
    - Cut State/HierarchyState -> via GraphicalEditor
    - Paste State/HierarchyState -> via GraphicalEditor
    - Refresh Libraries
    - Refresh All
    - Save as
    - Stop State Machine
    - Quit GUI
    """

    sm_manager_model = args[0]
    main_window_controller = args[1]
    menubar_ctrl = main_window_controller.get_controller('menu_bar_controller')

    current_sm_length = len(sm_manager_model.state_machines)
    first_sm_id = sm_manager_model.state_machines.keys()[0]
    call_gui_callback(menubar_ctrl.on_new_activate, None)

    assert len(sm_manager_model.state_machines) == current_sm_length + 1
    call_gui_callback(menubar_ctrl.on_open_activate, None, None, rafcon.__path__[0] + "/../test_scripts/tutorials/"
                                                                                      "basic_turtle_demo_sm")
    assert len(sm_manager_model.state_machines) == current_sm_length + 2

    sm_m = sm_manager_model.state_machines[first_sm_id + 2]
    sm_m.history.fake = True
    wait_for_gui()
    # MAIN_WINDOW NEEDS TO BE FOCUSED (for global input focus) TO OPERATE PASTE IN GRAPHICAL VIEWER
    main_window_controller.view['main_window'].grab_focus()
    sm_manager_model.selected_state_machine_id = first_sm_id + 2
    state_machines_ctrl = main_window_controller.get_controller('state_machines_editor_ctrl')
    page_id = state_machines_ctrl.get_page_id(first_sm_id + 2)
    page = state_machines_ctrl.view.notebook.get_nth_page(page_id)
    focus_graphical_editor_in_page(page)
    wait_for_gui()

    #########################################################
    # select & copy an execution state -> and paste it somewhere
    select_and_paste_state(sm_m, sm_m.get_state_model_by_path('CDMJPK/RMKGEW/KYENSZ'), sm_m.get_state_model_by_path(
        'CDMJPK/RMKGEW'), menubar_ctrl, 'copy', main_window_controller, page)

    ###########################################################
    # select & copy a hierarchy state -> and paste it some where
    select_and_paste_state(sm_m, sm_m.get_state_model_by_path('CDMJPK/RMKGEW/KYENSZ/VCWTIY'),
                           sm_m.get_state_model_by_path('CDMJPK'), menubar_ctrl, 'copy', main_window_controller, page)

    ##########################################################
    # select a library state -> and paste it some where WITH CUT !!!
    state_m, old_child_state_count = select_and_paste_state(sm_m,
                                                            sm_m.get_state_model_by_path('CDMJPK/RMKGEW/KYENSZ/VCWTIY'),
                                                            sm_m.get_state_model_by_path('CDMJPK'), menubar_ctrl, 'cut',
                                                            main_window_controller, page)

    ##########################################################
    # create complex state with all elements
    lib_state = LibraryState("generic/dialog", "Dialog [3 options]", "0.1", "Dialog [3 options]")
    call_gui_callback(statemachine_helper.insert_state, lib_state, True)
    assert len(state_m.state.states) == old_child_state_count + 2

    for state in state_m.state.states.values():
        if state.name == "Dialog [3 options]":
            break
    new_template_state = state
    call_gui_callback(new_template_state.add_scoped_variable, 'scoopy', float, 0.3)
    state_m_to_copy = sm_m.get_state_model_by_path('CDMJPK/' + new_template_state.state_id)

    ##########################################################
    # copy & paste complex state into itself
    copy_and_paste_state_into_itself(sm_m, state_m_to_copy, page, menubar_ctrl)
    # increase complexity by doing it twice -> increase the hierarchy-level
    copy_and_paste_state_into_itself(sm_m, state_m_to_copy, page, menubar_ctrl)

    call_gui_callback(menubar_ctrl.on_refresh_libraries_activate, None)
    call_gui_callback(menubar_ctrl.on_refresh_all_activate, None, None, True)
    assert len(sm_manager_model.state_machines) == 1

    call_gui_callback(menubar_ctrl.on_save_as_activate, None, None, testing_utils.get_unique_temp_path())
    call_gui_callback(menubar_ctrl.on_stop_activate, None)
    call_gui_callback(menubar_ctrl.on_quit_activate, None)


def test_gui(caplog):
    testing_utils.start_rafcon()
    testing_utils.remove_all_libraries()
    library_paths = rafcon.statemachine.config.global_config.get_config_value("LIBRARY_PATHS")
    gui_config.global_gui_config.set_config_value('HISTORY_ENABLED', False)
    gui_config.global_gui_config.set_config_value('AUTO_BACKUP_ENABLED', False)
    library_paths["ros"] = rafcon.__path__[0] + "/../test_scripts/ros_libraries"
    library_paths["turtle_libraries"] = rafcon.__path__[0] + "/../test_scripts/turtle_libraries"
    library_paths["generic"] = rafcon.__path__[0] + "/../libraries/generic"
    rafcon.statemachine.singleton.library_manager.refresh_libraries()

    [logger, ctr_state] = create_models()
    state_machine = StateMachine(ctr_state)
    rafcon.statemachine.singleton.state_machine_manager.add_state_machine(state_machine)
    testing_utils.sm_manager_model = rafcon.mvc.singleton.state_machine_manager_model
    main_window_view = MainWindowView()
    main_window_controller = MainWindowController(testing_utils.sm_manager_model, main_window_view,
                                                  editor_type='LogicDataGrouped')

    # Wait for GUI to initialize
    wait_for_gui()

    thread = threading.Thread(target=trigger_gui_signals, args=[testing_utils.sm_manager_model, main_window_controller])
    thread.start()
    gtk.main()
    logger.debug("after gtk main")
    thread.join()
    os.chdir(testing_utils.RAFCON_PATH + "/../test/common")
    testing_utils.test_multithrading_lock.release()
    testing_utils.assert_logger_warnings_and_errors(caplog)


if __name__ == '__main__':
    pytest.main(['-s', __file__])
