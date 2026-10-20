import QtQuick
import QtQuick.Effects
import Wavelane

/*!
    The round picture of an artist: their photo if they have one, else a tile with the
    first letter of the name, tinted from the name.
*/
Item {
    id: root

    //! Where the picture is on the server (empty when there is none).
    property string imagePath: ""
    property string name: ""
    property bool highlighted: false

    readonly property int hue: {
        let hash = 0
        for (let i = 0; i < name.length; ++i)
            hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
        return Math.abs(hash) % 360
    }

    // the letter, which also shows while the picture is on its way
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: Qt.hsla(root.hue / 360, 0.28, 0.2, 1.0)

        Text {
            anchors.centerIn: parent
            text: root.name ? root.name.charAt(0).toUpperCase() : "♪"
            color: Qt.hsla(root.hue / 360, 0.35, 0.62, 1.0)
            font.family: Theme.sans
            font.pixelSize: root.width * 0.42
            font.weight: Font.DemiBold
        }
    }

    Image {
        id: photo
        anchors.fill: parent
        anchors.margins: 1
        visible: false
        source: root.imagePath ? api.coverUrl(root.imagePath) : ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        sourceSize.width: Math.max(64, Math.round(root.width * 2))
        sourceSize.height: Math.max(64, Math.round(root.width * 2))
    }

    // the picture, cut to a circle
    Rectangle {
        id: circle
        anchors.fill: parent
        anchors.margins: 1
        radius: width / 2
        visible: false
        antialiasing: true
        layer.enabled: true
        layer.smooth: true
        layer.samples: 4
    }
    MultiEffect {
        anchors.fill: parent
        anchors.margins: 1
        source: photo
        visible: photo.status === Image.Ready
        maskEnabled: true
        maskSource: circle
        // a soft edge instead of a staircase of pixels
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
    }

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        antialiasing: true
        border.color: root.highlighted ? Theme.accent : Theme.borderStrong
        border.width: root.highlighted ? 2 : 1
    }
}
