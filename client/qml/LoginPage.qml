import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! Sign-in and registration, plus the server address. */
Item {
    id: root

    property bool registering: false

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.background }
            GradientStop { position: 1.0; color: "#121528" }
        }
    }

    ColumnLayout {
        anchors.centerIn: parent
        width: 380
        spacing: Theme.spacing

        ColumnLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: Theme.spacingLarge
            spacing: 6

            Canvas {
                Layout.alignment: Qt.AlignHCenter
                width: 64
                height: 44
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.reset()
                    ctx.lineWidth = 4
                    ctx.lineCap = "round"
                    const colors = [Theme.accent, Theme.accentAlt, Theme.accent]
                    for (let i = 0; i < 3; ++i) {
                        ctx.beginPath()
                        ctx.strokeStyle = colors[i]
                        const y = 10 + i * 12
                        ctx.moveTo(4, y)
                        ctx.bezierCurveTo(20, y - 9, 42, y + 9, 60, y)
                        ctx.stroke()
                    }
                }
            }

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Wavelane")
                color: Theme.text
                font.pixelSize: Theme.fontDisplay
                font.weight: Font.Bold
            }

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Ваша музыка. Ваша волна.")
                color: Theme.textMuted
                font.pixelSize: Theme.fontBody
            }
        }

        // --- server ---
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4

            Text {
                text: qsTr("Сервер")
                color: Theme.textMuted
                font.pixelSize: Theme.fontTiny
            }

            TextField {
                id: serverField
                Layout.fillWidth: true
                text: app.serverUrl
                placeholderText: "http://127.0.0.1:8000"
                color: Theme.text
                placeholderTextColor: Theme.textFaint
                selectByMouse: true
                font.pixelSize: Theme.fontSmall
                onEditingFinished: auth.setServerUrl(text)
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: Theme.surface
                    border.color: serverField.activeFocus ? Theme.accent : Theme.border
                    border.width: 1
                }
            }
        }

        TextField {
            id: emailField
            Layout.fillWidth: true
            visible: root.registering
            placeholderText: qsTr("Электронная почта")
            color: Theme.text
            placeholderTextColor: Theme.textFaint
            selectByMouse: true
            inputMethodHints: Qt.ImhEmailCharactersOnly
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.surface
                border.color: emailField.activeFocus ? Theme.accent : Theme.border
                border.width: 1
            }
        }

        TextField {
            id: loginField
            Layout.fillWidth: true
            text: root.registering ? "" : auth.lastLogin
            placeholderText: root.registering ? qsTr("Имя пользователя")
                                              : qsTr("Имя пользователя или почта")
            color: Theme.text
            placeholderTextColor: Theme.textFaint
            selectByMouse: true
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.surface
                border.color: loginField.activeFocus ? Theme.accent : Theme.border
                border.width: 1
            }
            Keys.onReturnPressed: submit()
        }

        TextField {
            id: passwordField
            Layout.fillWidth: true
            placeholderText: qsTr("Пароль")
            echoMode: TextInput.Password
            color: Theme.text
            placeholderTextColor: Theme.textFaint
            selectByMouse: true
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.surface
                border.color: passwordField.activeFocus ? Theme.accent : Theme.border
                border.width: 1
            }
            Keys.onReturnPressed: submit()
        }

        Text {
            Layout.fillWidth: true
            visible: auth.errorMessage !== ""
            text: auth.errorMessage
            color: Theme.negative
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }

        Button {
            id: submitButton
            Layout.fillWidth: true
            Layout.topMargin: 4
            enabled: !auth.busy
            text: auth.busy ? qsTr("Подождите…")
                            : (root.registering ? qsTr("Создать аккаунт") : qsTr("Войти"))

            contentItem: Text {
                text: submitButton.text
                color: "white"
                font.pixelSize: Theme.fontBody
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            background: Rectangle {
                implicitHeight: 42
                radius: Theme.radiusSmall
                opacity: submitButton.enabled ? 1.0 : 0.5
                gradient: Gradient {
                    GradientStop {
                        position: 0.0
                        color: submitButton.hovered ? Qt.lighter(Theme.accent, 1.15) : Theme.accent
                    }
                    GradientStop {
                        position: 1.0
                        color: submitButton.hovered ? Qt.lighter(Theme.accentAlt, 1.15)
                                                    : Theme.accentAlt
                    }
                }
            }

            onClicked: root.submit()
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 4
            text: root.registering ? qsTr("Уже есть аккаунт? Войти")
                                   : qsTr("Нет аккаунта? Зарегистрироваться")
            color: Theme.accent
            font.pixelSize: Theme.fontSmall

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    root.registering = !root.registering
                    auth.clearError()
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.topMargin: Theme.spacing
            visible: root.registering
            text: qsTr("Первый зарегистрированный аккаунт становится администратором сервера.")
            color: Theme.textFaint
            font.pixelSize: Theme.fontTiny
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }
    }

    function submit() {
        auth.setServerUrl(serverField.text)
        if (root.registering)
            auth.signUp(emailField.text, loginField.text, passwordField.text, "")
        else
            auth.signIn(loginField.text, passwordField.text)
    }
}
