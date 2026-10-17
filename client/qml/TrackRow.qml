import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! One track in a list. Used by every page, so it stays presentation-only. */
Rectangle {
    id: root

    // Roles supplied by TrackListModel.
    required property string trackId
    required property string title
    required property string artistName
    required property string coverPath
    required property string duration
    required property bool liked
    required property bool isExplicit
    required property string quality
    required property string reason

    property bool showReason: false
    property bool interactive: true
    property bool dimmed: false
    property bool playingNow: player.hasTrack && player.currentTrack.id === trackId

    signal activated()

    implicitHeight: 54
    radius: Theme.radiusSmall
    color: playingNow ? Theme.accentSoft
                      : (hover.containsMouse && interactive ? Theme.surfaceHover : "transparent")
    opacity: dimmed ? 0.55 : 1.0

    Behavior on color {
        ColorAnimation { duration: Theme.durationFast }
    }

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.interactive
        cursorShape: root.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor
        onDoubleClicked: root.activated()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: Theme.spacing

        CoverArt {
            Layout.preferredWidth: 38
            Layout.preferredHeight: 38
            coverPath: root.coverPath
            title: root.title
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: root.title
                    color: root.playingNow ? Theme.accent : Theme.text
                    font.pixelSize: Theme.fontBody
                    font.weight: root.playingNow ? Font.DemiBold : Font.Normal
                    elide: Text.ElideRight
                }

                Rectangle {
                    visible: root.isExplicit
                    width: 14; height: 14
                    radius: 3
                    color: Theme.surfaceActive
                    Text {
                        anchors.centerIn: parent
                        text: "E"
                        color: Theme.textMuted
                        font.pixelSize: 9
                        font.weight: Font.Bold
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Text {
                    text: root.artistName
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontTiny
                    elide: Text.ElideRight
                    Layout.maximumWidth: root.width * 0.45
                }

                Text {
                    visible: root.showReason && root.reason !== ""
                    text: "· " + root.reason
                    color: Theme.accent
                    font.pixelSize: Theme.fontTiny
                    elide: Text.ElideRight
                }

                Item { Layout.fillWidth: true }
            }
        }

        Text {
            visible: root.quality !== "" && hover.containsMouse
            text: root.quality
            color: Theme.textFaint
            font.pixelSize: Theme.fontTiny
        }

        IconButton {
            symbol: "♥"
            size: 28
            glyphSize: Theme.fontSmall
            visible: root.interactive && (hover.containsMouse || root.liked)
            active: root.liked
            activeColor: Theme.positive
            tooltip: root.liked ? qsTr("Убрать из избранного") : qsTr("Нравится")
            onClicked: library.toggleLike(root.trackId)
        }

        Text {
            text: root.duration
            color: Theme.textFaint
            font.pixelSize: Theme.fontTiny
            Layout.preferredWidth: 38
            horizontalAlignment: Text.AlignRight
        }
    }
}
