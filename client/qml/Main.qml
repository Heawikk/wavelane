import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

ApplicationWindow {
    id: window

    width: 1180
    height: 760
    minimumWidth: 880
    minimumHeight: 600
    visible: true
    title: qsTr("Wavelane")
    color: Theme.background

    // Which page the sidebar has selected.
    property int currentPage: 0

    Toast { id: toast }

    Connections {
        target: wave
        function onNotify(message) { toast.show(message) }
    }
    Connections {
        target: library
        function onNotify(message) { toast.show(message) }
    }
    Connections {
        target: player
        function onPlaybackFailed(message) { toast.show(message) }
    }

    Connections {
        target: auth
        function onSignedInChanged() {
            if (auth.signedIn) {
                window.currentPage = 0
                wave.loadSettings()
                library.loadStats()
                library.loadCatalogue()
            }
        }
    }

    // --- signed out -------------------------------------------------------

    LoginPage {
        anchors.fill: parent
        visible: !auth.signedIn
    }

    // --- signed in --------------------------------------------------------

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        visible: auth.signedIn

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // --- sidebar ---
            Rectangle {
                Layout.preferredWidth: Theme.sidebarWidth
                Layout.fillHeight: true
                color: Theme.surface

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacing
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.bottomMargin: Theme.spacingLarge
                        spacing: 10

                        // The logo: a small stack of wave lanes.
                        Canvas {
                            width: 30
                            height: 30
                            onPaint: {
                                const ctx = getContext("2d")
                                ctx.reset()
                                ctx.lineWidth = 3
                                ctx.lineCap = "round"
                                const colors = [Theme.accent, Theme.accentAlt, Theme.accent]
                                for (let i = 0; i < 3; ++i) {
                                    ctx.beginPath()
                                    ctx.strokeStyle = colors[i]
                                    const y = 8 + i * 7
                                    ctx.moveTo(3, y)
                                    ctx.bezierCurveTo(10, y - 6, 18, y + 6, 27, y)
                                    ctx.stroke()
                                }
                            }
                        }

                        Text {
                            text: qsTr("Wavelane")
                            color: Theme.text
                            font.pixelSize: Theme.fontTitle
                            font.weight: Font.DemiBold
                        }

                        Item { Layout.fillWidth: true }
                    }

                    Repeater {
                        model: [
                            { label: qsTr("Моя волна"), page: 0 },
                            { label: qsTr("Поиск"), page: 1 },
                            { label: qsTr("Коллекция"), page: 2 }
                        ]

                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 40
                            radius: Theme.radiusSmall
                            color: window.currentPage === modelData.page
                                   ? Theme.surfaceActive
                                   : (navMouse.containsMouse ? Theme.surfaceHover : "transparent")

                            Rectangle {
                                width: 3
                                height: parent.height * 0.5
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                radius: 2
                                color: Theme.accent
                                visible: window.currentPage === modelData.page
                            }

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 16
                                text: modelData.label
                                color: window.currentPage === modelData.page
                                       ? Theme.text : Theme.textMuted
                                font.pixelSize: Theme.fontBody
                                font.weight: window.currentPage === modelData.page
                                             ? Font.DemiBold : Font.Normal
                            }

                            MouseArea {
                                id: navMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    window.currentPage = modelData.page
                                    if (modelData.page === 2) {
                                        library.loadLiked()
                                        library.loadCatalogue()
                                    }
                                }
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 1
                        color: Theme.border
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        spacing: 8

                        Rectangle {
                            width: 30; height: 30; radius: 15
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: Theme.accent }
                                GradientStop { position: 1.0; color: Theme.accentAlt }
                            }
                            Text {
                                anchors.centerIn: parent
                                text: (auth.displayName || auth.username || "?")
                                      .charAt(0).toUpperCase()
                                color: "white"
                                font.pixelSize: Theme.fontSmall
                                font.weight: Font.Bold
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text {
                                Layout.fillWidth: true
                                text: auth.displayName || auth.username
                                color: Theme.text
                                font.pixelSize: Theme.fontSmall
                                elide: Text.ElideRight
                            }
                            Text {
                                visible: auth.isAdmin
                                text: qsTr("администратор")
                                color: Theme.textFaint
                                font.pixelSize: Theme.fontTiny
                            }
                        }

                        IconButton {
                            symbol: "⏻"
                            tooltip: qsTr("Выйти")
                            onClicked: auth.signOut()
                        }
                    }
                }
            }

            // --- content ---
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: window.currentPage

                WavePage {}
                SearchPage {}
                LibraryPage {}
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color: Theme.border
        }

        PlayerBar {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.playerBarHeight
        }
    }
}
