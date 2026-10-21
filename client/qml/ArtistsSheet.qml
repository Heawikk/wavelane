import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The artists of the playing track, on a sheet that slides up over the full player: their
    pictures, a line about each and a way to their page. The sheet is pulled down, or its
    arrow tapped, to put it away.
*/
Rectangle {
    id: root

    property bool opened: false

    signal closeRequested()

    // when put away it rests below the screen, so only its top edge ever shows while it moves
    y: opened ? 0 : parent.height
    visible: y < parent.height
    color: Theme.bg

    Behavior on y {
        NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
    }

    // swallow touches so the player underneath stays still
    MouseArea { anchors.fill: parent }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // the handle: drag it down or tap the arrow
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 64

            DragHandler {
                target: null
                yAxis.enabled: true
                xAxis.enabled: false
                onActiveChanged: if (!active && activeTranslation.y > 70) root.closeRequested()
            }

            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 8
                width: 40
                height: 4
                radius: 2
                color: Theme.borderStrong
            }
            Mono {
                anchors.left: parent.left
                anchors.leftMargin: 20
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 4
                text: library.playerArtists.length > 1 ? qsTr("Исполнители") : qsTr("Исполнитель")
                color: Theme.text
                font.weight: Font.DemiBold
                font.pixelSize: 13
            }
            IconButton {
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 4
                size: 48
                glyph: Theme.iChevronDown
                glyphSize: 22
                onClicked: root.closeRequested()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.border
        }

        ListView {
            id: list

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: library.playerArtists
            spacing: 0
            boundsBehavior: Flickable.StopAtBounds

            delegate: Item {
                id: card

                required property var modelData

                width: ListView.view.width
                height: body.implicitHeight + 40

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.border
                }

                ColumnLayout {
                    id: body
                    x: 20
                    y: 20
                    width: parent.width - 40
                    spacing: 14

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 16

                        ArtistAvatar {
                            Layout.preferredWidth: 88
                            Layout.preferredHeight: 88
                            imagePath: card.modelData.imagePath || ""
                            name: card.modelData.name
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            Text {
                                Layout.fillWidth: true
                                text: card.modelData.name
                                color: Theme.text
                                font.family: Theme.sans
                                font.pixelSize: 22
                                font.weight: Font.Bold
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                            }
                            Mono {
                                Layout.fillWidth: true
                                text: (card.modelData.role === "featured" ? qsTr("Участвует") : qsTr("Исполнитель"))
                                      + (card.modelData.trackCount > 0
                                         ? "  ·  " + card.modelData.trackCount + qsTr(" треков") : "")
                                      + (card.modelData.country ? "  ·  " + card.modelData.country : "")
                                color: Theme.faint
                                font.capitalization: Font.MixedCase
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: !!card.modelData.bio
                        text: card.modelData.bio || ""
                        color: Theme.muted
                        font.family: Theme.sans
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        lineHeight: 1.15
                    }

                    FlatButton {
                        Layout.preferredHeight: 40
                        horizontalPadding: 16
                        text: qsTr("Все треки")
                        onClicked: library.showArtist(card.modelData.id, card.modelData.name)
                    }
                }
            }
        }
    }
}
