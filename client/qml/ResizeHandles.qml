import QtQuick
import Wavelane

/*!
    Invisible grips along the window edges.

    Without the system frame there is nothing to grab, so each edge and corner
    gets a thin strip that asks the window system to start a resize. Using the
    system call rather than moving the window by hand keeps snapping and
    multi-monitor behaviour native.
*/
Item {
    id: root

    required property var window
    readonly property int grip: 5
    readonly property int corner: 12

    anchors.fill: parent
    z: 999
    visible: root.window.visibility !== Window.Maximized
             && root.window.visibility !== Window.FullScreen

    component Edge: MouseArea {
        property int edges: 0
        hoverEnabled: true
        onPressed: root.window.startSystemResize(edges)
    }

    // edges
    Edge {
        x: root.corner; y: 0
        width: root.width - 2 * root.corner; height: root.grip
        edges: Qt.TopEdge
        cursorShape: Qt.SizeVerCursor
    }
    Edge {
        x: root.corner; y: root.height - root.grip
        width: root.width - 2 * root.corner; height: root.grip
        edges: Qt.BottomEdge
        cursorShape: Qt.SizeVerCursor
    }
    Edge {
        x: 0; y: root.corner
        width: root.grip; height: root.height - 2 * root.corner
        edges: Qt.LeftEdge
        cursorShape: Qt.SizeHorCursor
    }
    Edge {
        x: root.width - root.grip; y: root.corner
        width: root.grip; height: root.height - 2 * root.corner
        edges: Qt.RightEdge
        cursorShape: Qt.SizeHorCursor
    }

    // corners
    Edge {
        x: 0; y: 0; width: root.corner; height: root.corner
        edges: Qt.TopEdge | Qt.LeftEdge
        cursorShape: Qt.SizeFDiagCursor
    }
    Edge {
        x: root.width - root.corner; y: 0; width: root.corner; height: root.corner
        edges: Qt.TopEdge | Qt.RightEdge
        cursorShape: Qt.SizeBDiagCursor
    }
    Edge {
        x: 0; y: root.height - root.corner; width: root.corner; height: root.corner
        edges: Qt.BottomEdge | Qt.LeftEdge
        cursorShape: Qt.SizeBDiagCursor
    }
    Edge {
        x: root.width - root.corner; y: root.height - root.corner
        width: root.corner; height: root.corner
        edges: Qt.BottomEdge | Qt.RightEdge
        cursorShape: Qt.SizeFDiagCursor
    }
}
