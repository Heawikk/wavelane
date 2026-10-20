import QtQuick
import Wavelane

/*!
    A heading over the cards of a search: the artists or the albums it found, as on
    Yandex Music. Artists get a round tile (a picture if they have one, else the first
    letter), albums their cover.

    On a desktop the cards fill one row and the rest wait behind "Показать все", which
    wraps all of them; on a phone the row scrolls sideways.
*/
Item {
    id: root

    property string heading: ""
    //! "artist" or "album"
    property string kind: "album"
    //! [{ id, name, imagePath }] for artists, [{ id, title, coverPath, year }] for albums.
    property var items: []
    property int cardSize: 148
    property int gap: 18
    property int margin: 16
    property bool scrollable: false
    property bool expanded: false

    signal picked(string id, string title)
    //! "Показать все" was pressed or undone, which changes how tall the shelf is.
    signal toggled()

    readonly property int capacity: Math.max(1, Math.floor((width - 2 * margin + gap) / (cardSize + gap)))
    readonly property bool hasMore: !scrollable && items.length > capacity
    readonly property int cardHeight: cardSize + 46

    // a new search starts folded again
    onItemsChanged: expanded = false

    visible: items.length > 0
    implicitHeight: visible ? headingText.height + body.height + 36 : 0

    Text {
        id: headingText
        x: root.margin
        y: 12
        text: root.heading
        color: Theme.text
        font.family: Theme.sans
        font.pixelSize: Theme.mobileIcons ? 18 : 20
        font.weight: Font.Bold
    }

    Mono {
        anchors.right: parent.right
        anchors.rightMargin: root.margin
        anchors.verticalCenter: headingText.verticalCenter
        visible: root.hasMore
        text: root.expanded ? qsTr("Свернуть") : qsTr("Показать все (%1)").arg(root.items.length)
        color: hover.containsMouse ? Theme.text : Theme.accentText

        MouseArea {
            id: hover
            anchors.fill: parent
            anchors.margins: -6
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                root.expanded = !root.expanded
                root.toggled()
            }
        }
    }

    // one card, shared by the two layouts below
    Component {
        id: cardComponent

        Item {
            id: card

            required property var modelData

            readonly property bool isArtist: root.kind === "artist"
            readonly property string cardTitle: isArtist ? modelData.name : modelData.title

            width: root.cardSize
            height: root.cardHeight

            Item {
                id: picture
                width: root.cardSize
                height: root.cardSize

                ArtistAvatar {
                    anchors.fill: parent
                    visible: card.isArtist
                    imagePath: card.isArtist ? (card.modelData.imagePath || "") : ""
                    name: card.cardTitle
                    highlighted: mouse.containsMouse
                }

                CoverArt {
                    anchors.fill: parent
                    visible: !card.isArtist
                    coverPath: card.isArtist ? "" : (card.modelData.coverPath || "")
                    title: card.cardTitle
                }
                Rectangle {
                    anchors.fill: parent
                    visible: !card.isArtist && mouse.containsMouse
                    color: "transparent"
                    border.color: Theme.accent
                    border.width: 2
                }
            }

            Text {
                anchors.top: picture.bottom
                anchors.topMargin: 8
                width: root.cardSize
                text: card.cardTitle
                color: Theme.text
                font.family: Theme.sans
                font.pixelSize: Theme.mobileIcons ? 14 : Theme.fontBody
                font.weight: Font.DemiBold
                horizontalAlignment: card.isArtist ? Text.AlignHCenter : Text.AlignLeft
                elide: Text.ElideRight
                maximumLineCount: 1
            }
            Text {
                anchors.top: picture.bottom
                anchors.topMargin: 8 + (Theme.mobileIcons ? 20 : 19)
                width: root.cardSize
                text: card.isArtist ? qsTr("Исполнитель") : (card.modelData.year || qsTr("Альбом"))
                color: Theme.faint
                font.family: Theme.sans
                font.pixelSize: Theme.mobileIcons ? 12 : Theme.fontSmall
                horizontalAlignment: card.isArtist ? Text.AlignHCenter : Text.AlignLeft
                elide: Text.ElideRight
                maximumLineCount: 1
            }

            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.picked(card.modelData.id, card.cardTitle)
            }
        }
    }

    Item {
        id: body

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: headingText.bottom
        anchors.topMargin: 12
        height: root.scrollable ? root.cardHeight : wrapped.height

        // phone: one row that scrolls sideways
        ListView {
            anchors.fill: parent
            visible: root.scrollable
            orientation: ListView.Horizontal
            spacing: root.gap
            leftMargin: root.margin
            rightMargin: root.margin
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: root.scrollable ? root.items : []
            delegate: cardComponent
        }

        // desktop: as many as fit in a row, or all of them wrapped
        Flow {
            id: wrapped

            x: root.margin
            width: parent.width - 2 * root.margin
            spacing: root.gap
            visible: !root.scrollable

            Repeater {
                model: root.scrollable ? [] : (root.expanded ? root.items
                                                             : root.items.slice(0, root.capacity))
                delegate: cardComponent
            }
        }
    }
}
