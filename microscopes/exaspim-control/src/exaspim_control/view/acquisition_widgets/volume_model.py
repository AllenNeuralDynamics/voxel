from pyqtgraph.opengl import GLImageItem
from PySide6.QtWidgets import (
    QMessageBox,
    QCheckBox,
    QGridLayout,
    QButtonGroup,
    QLabel,
    QRadioButton,
    QPushButton,
    QWidget,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QMatrix4x4, QVector3D, QQuaternion
from math import tan, radians, sqrt
import numpy as np
from scipy import spatial
from pyqtgraph import makeRGBA
from exaspim_control.view.miscellaneous_widgets.gl_ortho_view_widget import GLOrthoViewWidget
from exaspim_control.view.miscellaneous_widgets.gl_shaded_box_item import GLShadedBoxItem
from exaspim_control.view.miscellaneous_widgets.gl_path_item import GLPathItem


class SignalChangeVar:
    def __set_name__(self, owner, name):
        self.name = f'_{name}'

    def __set__(self, instance, value):
        setattr(instance, self.name, value)  # initially setting attr
        instance.valueChanged.emit(self.name[1:])

    def __get__(self, instance, value):
        return getattr(instance, self.name)


class VolumeModel(GLOrthoViewWidget):
    """Widget to display configured acquisition grid.  Note that the x and y refer to the tiling
    dimensions and z is the scanning dimension"""

    fov_dimensions = SignalChangeVar()
    fov_position = SignalChangeVar()
    grid_coords = SignalChangeVar()
    view_plane = SignalChangeVar()
    scan_volumes = SignalChangeVar()
    tile_visibility = SignalChangeVar()
    valueChanged = Signal(str)
    fovMove = Signal(list)
    fovHalt = Signal()

    def __init__(
        self,
        unit: str = 'mm',
        limits: list[tuple[float, float]] | None = None,
        fov_dimensions: list[float] | None = None,
        fov_position: list[float] | None = None,
        coordinate_plane: list[str] | None = None,
        fov_color: str = 'yellow',
        fov_line_width: int = 2,
        fov_opacity: float = 0.15,
        path_line_width: int = 2,
        path_arrow_size: float = 6.0,
        path_arrow_aspect_ratio: int = 4,
        path_start_color: str = 'yellow',
        path_end_color: str = 'green',
        active_tile_color: str = 'cyan',
        active_tile_opacity: float = 0.075,
        dual_active_tile_color: str = 'magenta',
        dual_active_tile_opacity: float = 0.075,
        inactive_tile_color: str = 'red',
        inactive_tile_opacity: float = 0.025,
        tile_line_width: int = 2,
        limits_line_width: int = 2,
        limits_color: str = 'white',
        limits_opacity: float = 0.1,
        dual_sided: bool = True,
    ):
        """
        GLViewWidget to display proposed grid of acquisition

        :param unit: unit of the volume model.
        :param coordinate_plane: coordinate plane displayed on widget.
        :param fov_dimensions: dimensions of field of view in coordinate plane
        :param fov_position: position of fov
        :param limits: list of limits ordered in [tile_dim[0], tile_dim[1], scan_dim[0]]
        :param fov_line_width: width of fov outline
        :param fov_line_width: width of fov outline
        :param fov_opacity: opacity of fov face where 1 is fully opaque
        :param path_line_width: width of path line
        :param path_arrow_size: size of arrow at the end of path as a percentage of the field of view
        :param path_arrow_aspect_ratio: aspect ratio of arrow
        :param path_start_color: start color of path
        :param path_end_color: end color of path
        :param active_tile_color: color of tiles when fov is within tile grid
        :param active_tile_opacity: opacity of active tile grid faces where 1 is fully opaque
        :param inactive_tile_color: color of tiles when fov is outside of tile grid
        :param inactive_tile_opacity: opacity of inactive tile grid faces where 1 is fully opaque
        :param tile_line_width: width of tiles
        :param limits_line_width: width of limits box
        :param limits_color: color of limits box
        :param limits_opacity: opacity of limits box
        """

        super().__init__(rotationMethod='quaternion')

        # initialize attributes
        self.unit = unit
        self.coordinate_plane = [x.replace('-', '') for x in coordinate_plane] if coordinate_plane else ['x', 'y', 'z']
        self.polarity = [1 if '-' not in x else -1 for x in coordinate_plane] if coordinate_plane else [1, 1, 1]
        self.fov_dimensions = fov_dimensions[:2] + [0] if fov_dimensions else [1.0, 1.0, 0]  # add 0 in the scanning dim
        self.fov_position = fov_position if fov_position else [0.0, 0.0, 0.0]
        self.view_plane = (self.coordinate_plane[0], self.coordinate_plane[1])  # plane currently being viewed

        self.scan_volumes = np.zeros([1, 1])  # 2d list detailing volume of tiles
        self.grid_coords = np.zeros([1, 1, 3])  # 2d list detailing start position of tiles
        self.start_tile_coord = np.zeros([1, 1, 3])
        self.end_tile_coord = np.zeros([1, 1, 3])
        self.grid_box_items = []  # 2D list detailing box items in grid
        self.tile_visibility = np.array([[True]])  # 2d list detailing visibility of tiles

        # tile aesthetic properties
        self.dual_sided = dual_sided
        self.active_tile_color = active_tile_color
        self.active_tile_opacity = active_tile_opacity
        self.dual_active_tile_color = dual_active_tile_color
        self.dual_active_tile_opacity = dual_active_tile_opacity
        self.inactive_tile_color = inactive_tile_color
        self.inactive_tile_opacity = inactive_tile_opacity
        self.tile_line_width = tile_line_width

        # limits aesthetic properties
        if not limits:
            limits = [(float('-inf'), float('inf')) for _ in range(3)]
        self.limits_line_width = limits_line_width
        self.limits_color = limits_color
        self.limits_opacity = limits_opacity

        # position data set externally since tiles are assumed out of order
        self.path = GLPathItem(
            width=path_line_width,
            arrow_size=path_arrow_size,
            arrow_aspect_ratio=path_arrow_aspect_ratio,
            path_start_color=path_start_color,
            path_end_color=path_end_color,
        )
        self.addItem(self.path)

        # initialize dict of fov_images
        self.fov_images = {}

        # initialize fov
        self.fov_view = GLShadedBoxItem(
            width=fov_line_width,
            pos=np.array([[self.fov_position]]),
            size=np.array(self.fov_dimensions),
            color=fov_color,
            opacity=fov_opacity,
            glOptions='additive',
        )
        self.fov_view.setTransform(
            QMatrix4x4(
                1,
                0,
                0,
                self.fov_position[0] * self.polarity[0],
                0,
                1,
                0,
                self.fov_position[1] * self.polarity[1],
                0,
                0,
                1,
                self.fov_position[2] * self.polarity[2],
                0,
                0,
                0,
                1,
            )
        )
        self.addItem(self.fov_view)

        if limits is not None and limits != [
            [float('-inf'), float('inf')],
            [float('-inf'), float('inf')],
            [float('-inf'), float('inf')],
        ]:
            size = [((max(limits[i]) - min(limits[i])) + self.fov_dimensions[i]) for i in range(3)]
            _ = np.array(
                [
                    [
                        [
                            min([x * self.polarity[0] for x in limits[0]]),
                            min([y * self.polarity[1] for y in limits[1]]),
                            min([z * self.polarity[2] for z in limits[2]]),
                        ]
                    ]
                ]
            )
            stage_limits = GLShadedBoxItem(
                width=self.limits_line_width,
                pos=np.array(
                    [
                        [
                            [
                                min([x * self.polarity[0] for x in limits[0]]),
                                min([y * self.polarity[1] for y in limits[1]]),
                                min([z * self.polarity[2] for z in limits[2]]),
                            ]
                        ]
                    ]
                ),
                size=np.array(size),
                color=self.limits_color,
                opacity=self.limits_opacity,
                glOptions='additive',
            )
            self.addItem(stage_limits)

        self.valueChanged.connect(self.update_model)
        self.resized.connect(self._update_opts)

        self._update_opts()

        # Add widgets for toggling view plane, path visibility, and halt stage
        self.widgets = QWidget()
        layout = QGridLayout()

        path_show = QCheckBox('Show Path')
        path_show.setChecked(True)
        path_show.toggled.connect(self.path.setVisible)
        layout.addWidget(path_show, 0, 0)

        layout.addWidget(QLabel('Plane View: '), 0, 1)
        view_plane = QButtonGroup()
        for i, view in enumerate(
            [
                f'({self.coordinate_plane[0]}, {self.coordinate_plane[2]})',
                f'({self.coordinate_plane[2]}, {self.coordinate_plane[1]})',
                f'({self.coordinate_plane[0]}, {self.coordinate_plane[1]})',
            ]
        ):
            button = QRadioButton(view)
            button.clicked.connect(lambda clicked, b=button: self.toggle_view_plane(b))
            view_plane.addButton(button)
            button.setChecked(True)
            layout.addWidget(button, 0, i + 2)

        halt = QPushButton('HALT STAGE')
        halt.pressed.connect(self.fovHalt.emit)
        layout.addWidget(halt, 1, 0, 1, 5)

        self.widgets.setLayout(layout)
        self.widgets.setMaximumHeight(70)
        self.widgets.show()

    def update_model(self, attribute_name) -> None:
        """Update attributes of grid
        :param attribute_name: name of attribute to update"""

        # update color of tiles based on z position
        flat_coords = self.grid_coords.reshape([-1, 3])  # flatten array
        flat_dims = self.scan_volumes.flatten()  # flatten array
        coords = np.concatenate((flat_coords, [[x, y, (z + sz)] for (x, y, z), sz in zip(flat_coords, flat_dims)]))
        extrema = [
            [min(coords[:, 0]), max(coords[:, 0])],
            [min(coords[:, 1]), max(coords[:, 1])],
            [min(coords[:, 2]), max(coords[:, 2])],
        ]

        # determine if fov is within grid
        in_grid = not any(pos > pos_max or pos < pos_min for (pos_min, pos_max), pos in zip(extrema, self.fov_position))

        # determine middle x coordinate
        center_line = np.mean(coords[:, 0])

        if attribute_name == 'fov_position':
            # update fov_pos
            self.fov_view.setTransform(
                QMatrix4x4(
                    1,
                    0,
                    0,
                    self.fov_position[0] * self.polarity[0],
                    0,
                    1,
                    0,
                    self.fov_position[1] * self.polarity[1],
                    0,
                    0,
                    1,
                    self.fov_position[2] * self.polarity[2],
                    0,
                    0,
                    0,
                    1,
                )
            )
            color = self.grid_box_items[0].color() if len(self.grid_box_items) != 0 else None
            if (not in_grid and color != self.inactive_tile_color) or (in_grid and color != self.active_tile_color):
                for box_ind, box in enumerate(self.grid_box_items):
                    if in_grid:
                        new_color = (
                            self.active_tile_color
                            if coords[box_ind, 0] < center_line or not self.dual_sided
                            else self.dual_active_tile_color
                        )
                    else:
                        new_color = self.inactive_tile_color
                    box.setColor(color=new_color)
        else:
            self.fov_view.setSize(x=self.fov_dimensions[0], y=self.fov_dimensions[1], z=0.0)

            # faster to remove every box than parse which ones have changes
            for box in self.grid_box_items:
                self.removeItem(box)
            self.grid_box_items = []

            total_rows = len(self.grid_coords)
            total_columns = len(self.grid_coords[0])

            for row in range(total_rows):
                for column in range(total_columns):
                    coord = [x * pol for x, pol in zip(self.grid_coords[row][column], self.polarity)]
                    size = [*self.fov_dimensions[:2], self.scan_volumes[row, column]]

                    # determine color
                    if in_grid:
                        color = (
                            self.active_tile_color
                            if coord[0] < center_line or not self.dual_sided
                            else self.dual_active_tile_color
                        )
                        opacity = (
                            self.active_tile_opacity
                            if coord[0] < center_line or not self.dual_sided
                            else self.dual_active_tile_opacity
                        )
                    else:
                        color = self.inactive_tile_color
                        opacity = self.inactive_tile_opacity

                    # scale opacity for viewing
                    if self.view_plane == (self.coordinate_plane[2], self.coordinate_plane[1]):
                        opacity = opacity / total_columns
                    elif self.view_plane != (self.coordinate_plane[0], self.coordinate_plane[1]):
                        opacity = opacity / total_rows

                    box = GLShadedBoxItem(
                        width=self.tile_line_width,
                        pos=np.array([[coord]]),
                        size=np.array(size),
                        color=color,
                        opacity=opacity,
                        glOptions='additive',
                    )
                    box.setVisible(self.tile_visibility[row, column])
                    self.addItem(box)
                    self.grid_box_items.append(box)

        self._update_opts()

    def toggle_view_plane(self, button) -> None:
        """
        Update view plane optics
        :param button: button pressed to change view
        """

        view_plane = tuple(x for x in button.text() if x.isalpha())
        self.view_plane = view_plane

    def set_path_pos(self, coord_order: list) -> None:
        """Set the pos of path in correct order
        :param coord_order: ordered list of coords for path"""

        path = np.array(
            [
                [
                    ((coord[i] * pol) + (0.5 * fov))
                    for i, fov, pol, x in zip([0, 1, 2], self.fov_dimensions, self.polarity, self.coordinate_plane)
                ]
                for coord in coord_order
            ]
        )
        self.path.setData(pos=path)

    def add_fov_image(self, image: np.ndarray, levels: list[float]) -> None:
        """add image to model assuming image has same fov dimensions and orientation
        :param image: numpy array of image to display in model
        :param levels: levels for passed in image"""

        image_rgba = makeRGBA(image, levels=levels)
        image_rgba[0][:, :, 3] = 200

        gl_image = GLImageItem(image_rgba[0], glOptions='additive')
        x, y, z = self.fov_position
        gl_image.setTransform(
            QMatrix4x4(
                self.fov_dimensions[0] / image.shape[0],
                0,
                0,
                x * self.polarity[0],
                0,
                self.fov_dimensions[1] / image.shape[1],
                0,
                y * self.polarity[1],
                0,
                0,
                1,
                z * self.polarity[2],
                0,
                0,
                0,
                1,
            )
        )
        self.addItem(gl_image)
        self.fov_images[image.tobytes()] = gl_image

        if self.view_plane != (self.coordinate_plane[0], self.coordinate_plane[1]):
            gl_image.setVisible(False)

    def adjust_glimage_contrast(self, image: np.ndarray, contrast_levels: list[float]) -> None:
        """
        Adjust image in model contrast levels
        :param image: numpy array of image key in fov_images
        :param contrast_levels: levels for passed in image
        """

        if image.tobytes() in self.fov_images:  # check if image has been deleted
            glimage = self.fov_images[image.tobytes()]
            _ = [glimage.transform()[i, 3] / pol for i, pol in zip(range(3), self.polarity)]
            self.removeItem(glimage)
            self.add_fov_image(image, contrast_levels)

    def toggle_fov_image_visibility(self, visible: bool) -> None:
        """Function to hide all fov_images
        :param visible: boolean for if fov_images should be visible"""

        for image in self.fov_images.values():
            image.setVisible(visible)

    def _update_opts(self) -> None:
        """Update view of widget. Note that x/y notation refers to horizontal/vertical dimensions of grid view"""

        view_plane = self.view_plane
        view_pol = [
            self.polarity[self.coordinate_plane.index(view_plane[0])],
            self.polarity[self.coordinate_plane.index(view_plane[1])],
        ]
        coords = self.grid_coords.reshape([-1, 3])  # flatten array
        dimensions = self.scan_volumes.flatten()  # flatten array

        # set rotation
        root = sqrt(2.0) / 2.0
        if view_plane == (self.coordinate_plane[0], self.coordinate_plane[1]):
            self.opts['rotation'] = QQuaternion(-1, 0, 0, 0)
        else:
            self.opts['rotation'] = (
                QQuaternion(-root, 0, -root, 0)
                if view_plane == (self.coordinate_plane[2], self.coordinate_plane[1])
                else QQuaternion(-root, root, 0, 0)
            )
            # take into account end of tile and account for difference in size if z included in view
            coords = np.concatenate((coords, [[x, y, (z + sz)] for (x, y, z), sz in zip(coords, dimensions)]))

        extrema = {
            f'{self.coordinate_plane[0]}_min': min(coords[:, 0]),
            f'{self.coordinate_plane[0]}_max': max(coords[:, 0]),
            f'{self.coordinate_plane[1]}_min': min(coords[:, 1]),
            f'{self.coordinate_plane[1]}_max': max(coords[:, 1]),
            f'{self.coordinate_plane[2]}_min': min(coords[:, 2]),
            f'{self.coordinate_plane[2]}_max': max(coords[:, 2]),
        }

        fov = dict(zip(self.coordinate_plane, self.fov_dimensions))
        pos = dict(zip(self.coordinate_plane, self.fov_position))
        distances = {
            self.coordinate_plane[0] + self.coordinate_plane[1]: [
                sqrt((pos[view_plane[0]] - x) ** 2 + (pos[view_plane[1]] - y) ** 2) for x, y, z in coords
            ],
            self.coordinate_plane[0] + self.coordinate_plane[2]: [
                sqrt((pos[view_plane[0]] - x) ** 2 + (pos[view_plane[1]] - z) ** 2) for x, y, z in coords
            ],
            self.coordinate_plane[2] + self.coordinate_plane[1]: [
                sqrt((pos[view_plane[0]] - z) ** 2 + (pos[view_plane[1]] - y) ** 2) for x, y, z in coords
            ],
        }
        max_index = distances[''.join(view_plane)].index(max(distances[''.join(view_plane)], key=abs))
        furthest_tile = {
            self.coordinate_plane[0]: coords[max_index][0],
            self.coordinate_plane[1]: coords[max_index][1],
            self.coordinate_plane[2]: coords[max_index][2],
        }
        center = {}

        # Horizontal sizing, if fov_position is within grid or farthest distance is between grid tiles
        opts_fov = float(self.opts['fov']) if isinstance(self.opts['fov'], (float, int)) else 0.0
        x = view_plane[0]
        if extrema[f'{x}_min'] <= pos[x] <= extrema[f'{x}_max'] or abs(furthest_tile[x] - pos[x]) < abs(
            extrema[f'{x}_max'] - extrema[f'{x}_min']
        ):
            center[x] = (((extrema[f'{x}_min'] + extrema[f'{x}_max']) / 2) + (fov[x] / 2 * view_pol[0])) * view_pol[0]
            horz_dist = ((extrema[f'{x}_max'] - extrema[f'{x}_min']) + (fov[x] * 2)) / 2 * tan(radians(opts_fov))
        else:
            center[x] = (((pos[x] + furthest_tile[x]) / 2) + (fov[x] / 2 * view_pol[0])) * view_pol[0]
            horz_dist = (abs(pos[x] - furthest_tile[x]) + (fov[x] * 2)) / 2 * tan(radians(opts_fov))
        # Vertical sizing, if fov_position is within grid or farthest distance is between grid tiles
        y = view_plane[1]
        scaling = self.size().width() / self.size().height()
        if extrema[f'{y}_min'] <= pos[y] <= extrema[f'{y}_max'] or abs(furthest_tile[y] - pos[y]) < abs(
            extrema[f'{y}_max'] - extrema[f'{y}_min']
        ):
            center[y] = (((extrema[f'{y}_min'] + extrema[f'{y}_max']) / 2) + (fov[y] / 2 * view_pol[1])) * view_pol[1]
            # View doesn't scale when changing vertical size so take into account the dif between the height and width
            vert_dist = (
                ((extrema[f'{y}_max'] - extrema[f'{y}_min']) + (fov[y] * 2)) / 2 * tan(radians(opts_fov)) * scaling
            )
        else:
            center[y] = (((pos[y] + furthest_tile[y]) / 2) + (fov[y] / 2 * view_pol[1])) * view_pol[1]
            vert_dist = (abs(pos[y] - furthest_tile[y]) + (fov[y] * 2)) / 2 * tan(radians(opts_fov)) * scaling
        # @Micah in ortho mode it seems to scale properly with x1200... not sure how to explain why though
        # not sure if this actually works, and whether it needs to be copied to other places in the fx
        self.opts['distance'] = horz_dist * 1200 if horz_dist > vert_dist else vert_dist * 1200

        self.opts['center'] = QVector3D(  # type: ignore
            center.get(self.coordinate_plane[0], 0),
            center.get(self.coordinate_plane[1], 0),
            center.get(self.coordinate_plane[2], 0),
        )

        self.update()

    def move_fov_query(self, new_fov_pos: list[float]) -> tuple[int, bool]:
        """Message box asking if user wants to move fov position
        :param new_fov_pos: position to move the fov to in um
        :return: user reply to pop up and whether to move to the tile nearest the new_fov_pos
        """
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Icon.Question)
        msgBox.setText(
            f'Do you want to move the field of view from '
            f'{[round(float(x), 2) for x in self.fov_position]} [{self.unit}] to '
            f'{[round(float(x), 2) for x in new_fov_pos]} [{self.unit}]?'
        )
        msgBox.setWindowTitle('Moving FOV')
        msgBox.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        checkbox = QCheckBox('Move to nearest tile')
        checkbox.setChecked(True)
        msgBox.setCheckBox(checkbox)

        return msgBox.exec(), checkbox.isChecked()

    def delete_fov_image_query(self, fov_image_pos: list[float]) -> int:
        """Message box asking if user wants to move fov position
        :param fov_image_pos: coordinates of fov image
        :return: user reply to deleting image"""

        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Icon.Question)
        msgBox.setText(f'Do you want to delete image at {fov_image_pos} [{self.unit}]?')
        msgBox.setWindowTitle('Deleting FOV Image')
        msgBox.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        return msgBox.exec()

    def mousePressEvent(self, ev) -> None:
        """Override mousePressEvent so user can't change view
        and allow user to move fov easier
        :param ev: QMouseEvent of users mouse"""

        plane = list(self.view_plane) + [ax for ax in self.coordinate_plane if ax not in self.view_plane]
        view_pol = [
            self.polarity[self.coordinate_plane.index(plane[0])],
            self.polarity[self.coordinate_plane.index(plane[1])],
            self.polarity[self.coordinate_plane.index(plane[2])],
        ]
        # Translate mouseclick x, y into view widget coordinate plane.
        distance = float(self.opts['distance']) if isinstance(self.opts['distance'], (float, int)) else 0.0
        fov = float(self.opts['fov']) if isinstance(self.opts['fov'], (float, int)) else 0.0
        horz_dist = (distance / tan(radians(fov))) / 1200
        vert_dist = (
            (
                float(self.opts['distance']) / tan(radians(float(self.opts['fov'])))
                if isinstance(self.opts['distance'], (float, int)) and isinstance(self.opts['fov'], (float, int))
                else 0.0
            )
            * (self.size().height() / self.size().width())
        ) / 1200
        horz_scale = (ev.x() * 2 * horz_dist) / self.size().width()
        vert_scale = (ev.y() * 2 * vert_dist) / self.size().height()

        # create dictionaries of from fov and pos
        fov = dict(zip(self.coordinate_plane, self.fov_dimensions))
        pos = dict(zip(self.coordinate_plane, self.fov_position))

        opts_center = self.opts['center']
        if isinstance(opts_center, (QVector3D)):
            center = {
                self.coordinate_plane[0]: opts_center.x(),
                self.coordinate_plane[1]: opts_center.y(),
                self.coordinate_plane[2]: opts_center.z(),
            }
        else:
            center = {
                self.coordinate_plane[0]: 0,
                self.coordinate_plane[1]: 0,
                self.coordinate_plane[2]: 0,
            }
        h_ax = self.view_plane[0]
        v_ax = self.view_plane[1]

        new_pos = {
            plane[0]: ((center[h_ax] - horz_dist + horz_scale) - 0.5 * fov[plane[0]]) * view_pol[0],
            plane[1]: ((center[v_ax] + vert_dist - vert_scale) - 0.5 * fov[plane[1]]) * view_pol[1],
            plane[2]: pos[plane[2]] * view_pol[2],
        }
        move_to = [new_pos[ax] for ax in self.coordinate_plane]
        if ev.button() == Qt.MouseButton.LeftButton:
            return_value, checkbox = self.move_fov_query(move_to)

            if return_value == QMessageBox.StandardButton.Ok:
                if not checkbox:  # Move to exact location
                    pos = move_to
                else:  # move to the nearest tile
                    flattened = self.grid_coords.reshape([-1, 3])
                    tree = spatial.KDTree(self.grid_coords.reshape([-1, 3]))
                    distance, index = tree.query(move_to)
                    tile = flattened[index]
                    pos = [tile[0], tile[1], tile[2]]
                self.fovMove.emit(pos)

            else:
                return

        elif ev.button() == Qt.MouseButton.RightButton:
            delete_key = None
            for key, image in self.fov_images.items():
                coords = [image.transform()[i, 3] for i in range(3)]
                if (
                    coords[0] - self.fov_dimensions[0] <= coords[0] <= coords[0] + self.fov_dimensions[0]
                    and coords[1] - self.fov_dimensions[1] <= coords[1] <= coords[1] + self.fov_dimensions[1]
                ):
                    return_value = self.delete_fov_image_query(coords)
                    if return_value == QMessageBox.StandardButton.Ok:
                        self.removeItem(image)
                        delete_key = key
                    break
            if delete_key is not None:
                del self.fov_images[delete_key]

    def mouseMoveEvent(self, ev):
        """Override mouseMoveEvent so user can't change view"""
        pass

    def wheelEvent(self, ev):
        """Override wheelEvent so user can't change view"""
        pass

    def keyPressEvent(self, ev):
        """Override keyPressEvent so user can't change view"""
        pass

    def keyReleaseEvent(self, ev):
        """Override keyReleaseEvent so user can't change view"""
        pass
