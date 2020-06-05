
#-------------------------------------------------------------------------------
# Name:     Arboretum
# Purpose:  Dockable widget, and custom track visualization layers for Napari,
#           to cell/object track data.
#
# Authors:  Alan R. Lowe (arl) a.lowe@ucl.ac.uk
#
# License:  See LICENSE.md
#
# Created:  01/05/2020
#-------------------------------------------------------------------------------

import os
import enum
import heapq

import numpy as np

import napari
from napari.qt.threading import thread_worker

from typing import Union

from .manager import TrackManager
from .layers.tracks import Tracks

from ._colormaps import colormaps



def _register_tracks_layer():
    """ _register_tracks_layer

    This can be used to register the custom arboretum Tracks layers with
    Napari.

    Notes:
        This is HACKTASTIC!

    """
    from .layers.tracks.vispy_tracks_layer import VispyTracksLayer
    from .layers.tracks.qt_tracks_layer import QtTracksControls

    # NOTE(arl): use this code to register a vispy function for the tracks layer
    napari._vispy.utils.layer_to_visual[Tracks] = VispyTracksLayer
    napari._qt.layers.utils.layer_to_controls[Tracks] = QtTracksControls







def build_plugin(viewer, tracks):

    # register the custom layers with this napari instance
    _register_tracks_layer()

    # build a track manager
    if isinstance(tracks, TrackManager):
        manager = tracks
    else:
        manager = TrackManager(tracks)

    # add the arboretum tracks layer
    track_layer = Tracks(name='Tracks',
                         data=manager.data,
                         properties=manager.properties,
                         colormaps=colormaps)
    viewer.add_layer(track_layer)




def build_plugin_v2(viewer,
                    segmentation: Union[None, np.ndarray] = None):
    """ build the plugin

    Arguments:
        viewer: an instance of the napari viewer
        segmentation: optional segmentation to be loaded as as a `labels` layer

    """

    from .plugin import Arboretum
    from . import utils

    # register the custom layers with this napari instance
    _register_tracks_layer()

    # build the plugin
    arbor = Arboretum()

    # add the widget to Napari
    viewer.window.add_dock_widget(arbor,
                                  name='arboretum',
                                  area='right')

    # name a new layer using the source layer
    new_layer_name = lambda s: f'{s} {arbor.active_layer}'

    # callbacks to add layers
    def add_segmentation_layer(editable:bool = False):
        """ add a segmentation layer """
        if arbor.segmentation is not None:
            seg_layer = viewer.add_labels(arbor.segmentation, name='Segmentation')
            seg_layer.editable = editable

    def add_localizations_layer():
        """ add a localizations layer """
        if arbor.localizations is not None:
            pts_layer = viewer.add_points(arbor.localizations[:,:3],
                                          name=new_layer_name('Localizations'),
                                          face_color='b')
    def add_track_layer():
        """ add a track layer """
        if arbor.tracks is not None:
            for i, track_set in enumerate(arbor.tracks):

                # build a track manager
                manager = TrackManager(track_set)

                _trk_layer = Tracks(data=manager.data,
                                    properties=manager.properties,
                                    name=new_layer_name(f'Tracks {i}'),
                                    colormaps=colormaps)
                track_layer = viewer.add_layer(_trk_layer)


    def add_segmentation_and_track_layers():
        """ TODO(arl): oof """
        add_segmentation_layer()
        add_track_layer()

    def import_objects():
        """ wrapper to load objects/tracks """

        @thread_worker
        def _import():
            """ import track data """
            # get the extension, and pick the correct file loader
            if arbor.filename is not None:
                seg, tracks = utils.load_hdf(arbor.filename)
                arbor.segmentation = seg
                arbor.tracks = tracks

        worker = _import()
        worker.returned.connect(add_segmentation_and_track_layers)
        worker.start()



    def localize_objects():
        """ wrapper to localizer objects """

        @thread_worker
        def _localize():
            """ localize objects using the currently selected layer """
            arbor.active_layer = viewer.active_layer
            arbor.segmentation = viewer.layers[viewer.active_layer]
            arbor.status_label.setText('Localizing...')
            arbor.localizations = utils.localize(arbor.segmentation)
            arbor.status_label.setText('')

        worker = _localize()
        worker.returned.connect(add_localizations_layer)
        worker.start()



    def track_objects():
        """ wrapper to launch a tracking thread """

        @thread_worker
        def _track():
            """ track objects """
            if arbor.localizations is not None:
                optimize = arbor.optimize_checkbox.isChecked()
                arbor.status_label.setText('Tracking...')
                tracker_state = utils.track(arbor.localizations,
                                            arbor.btrack_cfg,
                                            optimize=optimize,
                                            volume=arbor.volume)
                arbor.tracker_state = tracker_state
                arbor.status_label.setText('')

        worker = _track()
        worker.returned.connect(add_track_layer)
        worker.start()





    # if we loaded some data add both the segmentation and tracks layer
    arbor.load_button.clicked.connect(import_objects)

    # do some localization using the currently selected segmentation
    arbor.localize_button.clicked.connect(localize_objects)

    # do some tracking using the currently selected localizations
    arbor.track_button.clicked.connect(track_objects)

    # if we're passing a segmentation, add it as a labels layer
    if segmentation is not None:
        arbor.segmentation = segmentation
        add_segmentation_layer(editable=True)





def run(**kwargs):
    """ run an instance of napari with the plugin """
    with napari.gui_qt():
        viewer = napari.Viewer()
        build_plugin_v2(viewer, **kwargs)
