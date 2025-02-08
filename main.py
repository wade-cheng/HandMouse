import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import threading

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False

# alias mediapipe utilities
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

# set up constants and helpers
# pixels
SCREEN_RESOLUTION: tuple[int, int] = 1920, 1080
INDEX_HELD = False
MIDDLE_HELD = False
MOUSE_DOWN = False
# buffer time to decide if a finger down is a click or hold (prio hold)
MOUSE_DOWN_LENIENCY_TIME = 0.25
# like our "mouse sensitivity" but we aren't using a mouse are we
MOVEMENT_SENSE: float = 2


def xytransform(xy: tuple[float, float]) -> np.ndarray:
    x, y = xy
    xy = np.array([x, y])
    return (xy - 0.5) * MOVEMENT_SENSE + 0.5


class PosInterp:
    """
    use a rotating array to keep track of the last interp_length, given inputs

    interpolates between these values and decide if we have a click
    """

    def __init__(self, interp_length: int):
        self._INTERP_LENGTH = interp_length
        self._inner = np.tile(np.array([0.5, 0.5]), (self._INTERP_LENGTH, 1))
        self._i = 0

    def push_pos(self, xy: np.ndarray):
        """xy should be shape 1x2 to denote x,y"""
        self._inner[self._i] = xy
        self._i = (self._i + 1) % self._INTERP_LENGTH

    def get_cursor_pos(self) -> np.ndarray:
        """
        gets the current cursor pos, given the interpolation cache, by taking the average of the rows.
        i.e., sums down the columns to a 1x2 matrix, then divides by length.
        """
        return np.sum(self._inner, axis=0) / self._INTERP_LENGTH


class ClickInterp:
    """
    use a rotating array to keep track of the last interp_length, given inputs

    interpolates between these values and decide if we have a click
    """

    def __init__(self, interp_length: int):
        self._INTERP_LENGTH = interp_length
        self._inner = np.zeros(self._INTERP_LENGTH, dtype=bool)
        self._i = 0

    def push_click(self, clicking: bool):
        self._inner[self._i] = clicking
        self._i = (self._i + 1) % self._INTERP_LENGTH

    def get_clicking(self) -> bool:
        """
        returns whether we are clicking based on our interpolation cache
        """
        return np.sum(self._inner) / self._INTERP_LENGTH > 0.5


mouse_poses = PosInterp(interp_length=5)
index_poses = ClickInterp(interp_length=5)
middle_poses = ClickInterp(interp_length=5)
ring_poses = ClickInterp(interp_length=5)
pinkie_poses = ClickInterp(interp_length=5)


def try_click_left():
    if not MOUSE_DOWN:
        pyautogui.click(button="left")


def try_click_right():
    if not MOUSE_DOWN:
        pyautogui.click(button="right")


# For webcam input:
cap = cv2.VideoCapture(0)
with mp_hands.Hands(
    model_complexity=0, min_detection_confidence=0.5, min_tracking_confidence=0.5
) as hands:
    while cap.isOpened():
        success, image = cap.read()
        if not success:
            print("Ignoring empty camera frame.")
            # If loading a video, use 'break' instead of 'continue'.
            continue

        # To improve performance, optionally mark the image as not writeable to
        # pass by reference.
        image.flags.writeable = False
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = hands.process(image)

        if results.multi_hand_landmarks:
            # process hand data
            wrist = results.multi_hand_landmarks[0].landmark[0]
            mouse_poses.push_pos(xytransform((wrist.x, wrist.y)))
            index_poses.push_click(
                results.multi_hand_landmarks[0].landmark[8].y
                > results.multi_hand_landmarks[0].landmark[6].y
            )
            middle_poses.push_click(
                results.multi_hand_landmarks[0].landmark[12].y
                > results.multi_hand_landmarks[0].landmark[10].y
            )
            ring_poses.push_click(
                results.multi_hand_landmarks[0].landmark[16].y
                > results.multi_hand_landmarks[0].landmark[14].y
            )
            pinkie_poses.push_click(
                results.multi_hand_landmarks[0].landmark[20].y
                > results.multi_hand_landmarks[0].landmark[18].y
            )

            # use processed hand data to do actions
            x, y = mouse_poses.get_cursor_pos().tolist()
            pyautogui.moveTo(
                SCREEN_RESOLUTION[0] - x * SCREEN_RESOLUTION[0],
                y * SCREEN_RESOLUTION[1],
            )

            if INDEX_HELD and not index_poses.get_clicking():
                INDEX_HELD = False
            if not INDEX_HELD and index_poses.get_clicking():
                INDEX_HELD = True
                threading.Timer(MOUSE_DOWN_LENIENCY_TIME, try_click_left).start()

            if MIDDLE_HELD and not middle_poses.get_clicking():
                MIDDLE_HELD = False
            if not MIDDLE_HELD and middle_poses.get_clicking():
                MIDDLE_HELD = True
                threading.Timer(MOUSE_DOWN_LENIENCY_TIME, try_click_right).start()

            if all(
                x.get_clicking()
                for x in [index_poses, middle_poses, ring_poses, pinkie_poses]
            ):
                if not MOUSE_DOWN:
                    pyautogui.mouseDown()
                    MOUSE_DOWN = True
            else:
                if MOUSE_DOWN:
                    pyautogui.mouseUp()
                    MOUSE_DOWN = False

        # Draw the hand annotations on the image.
        image.flags.writeable = True
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(
                    image,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style(),
                )
        # Flip the image horizontally for a selfie-view display.
        # TODO: replace "" with title if wanted
        cv2.imshow("", cv2.flip(image, 1))
        if cv2.waitKey(5) & 0xFF == ord("q"):
            cap.release()
