#pragma once


// TL50 Pro Tower Light with USB: Microsoft Windows native interface header
// Version 1.0
// Copyright (c) 2020 by Banner Engineering Corp.

#ifdef __cplusplus 
extern "C" {
#endif

/// <summary>Initialize communications.  Init is needed before communicationg with the device.</summary>
/// <returns>On success, returns the number of the COM port used.  Otherwise a <c>CommReturnValue</c> describing the status of the command.</returns>
/// <remarks>Will automatically pick a COM port to use.</remarks>
/// <remarks>Will cause a persistance to the device.</remarks>
__declspec(dllimport) int Init();

/// <summary>Initialize communications.  Init is needed before communicationg with the device.</summary>
/// <param name="comPortNumber">The COM port to use, e.g. 6 means COM6.</param>
/// <returns>On success, returns the number of the COM port used.  Otherwise a <c>CommReturnValue</c> describing the status of the command.</returns>
/// <remarks>Will cause a persistance to the device.</remarks>
__declspec(dllimport) int InitByPort(int comPortNumber);

/// <summary>Turn a segment on to a steady color.</summary>
/// <param name="segment">The 0-based index of the segment to change (0-9).</param>
/// <param name="color">The color of the indication.  See <c>enum Color</c> for values.</param>
/// <returns>A <c>CommReturnValue</c> describing the status of the command.</returns>
/// <remarks>This setting is not persisted across power cycles.</remarks>
__declspec(dllimport) int SetSegmentSolid(int segment, int color);

/// <summary>Turn off indication of a segment.</summary>
/// <param name="segment">The 0-based index of the segment to change (0-9).</param>
/// <returns>A <c>CommReturnValue</c> describing the status of the command.</returns>
/// <remarks>This setting is not persisted across power cycles.</remarks>
__declspec(dllimport) int SetSegmentOff(int segment);

/// <summary>Stops using the COM port acquired with <see cref="Init"/> or <see cref="InitByPort"/>.</summary>
/// <returns>A <c>CommReturnValue</c> describing the status of the command.</returns>
__declspec(dllimport) int Deinit();

/// <summary>The version of this library.</summary>
/// <returns>A <c>CommReturnValue</c> describing the status of the command.</returns>
/// <remarks>The most-significant byte is the major version, the least-significant byte is the minor version.</remarks>
__declspec(dllimport) unsigned short GetDllVersion();

/// <summary>The available colors for indication.</summary>
enum Color
{
	GREEN = 0,
	RED = 1,
	ORANGE = 2,
	AMBER = 3,
	YELLOW = 4,
	LIME_GREEN = 5,
	SPRING_GREEN = 6,
	CYAN = 7,
	SKY_BLUE = 8,
	BLUE = 9,
	VIOLET = 10,
	MAGENTA = 11,
	ROSE = 12,
	WHITE = 13,
	/// <summary>Used with <c>SetCustomColor1</c>.</summary>
	CUSTOM_COLOR_1 = 14,
	/// <summary>Used with <c>SetCustomColor2</c>.</summary>
	CUSTOM_COLOR_2 = 15
};

/// <summary>The styles of indication available for individual segments.</summary>
enum SegmentAnimation
{
	/// <summary>No indication.</summary>
	SEGMENT_OFF = 0,
	/// <summary>A single solid color.</summary>
	SEGMENT_STEADY = 1,
	/// <summary>A single color blinks off and on.</summary>
	SEGMENT_FLASH = 2,
	/// <summary>Switches between two different colors.</summary>
	SEGMENT_TWO_COLOR_FLASH = 3,
	/// <summary>The indication is split between two colors.</summary>
	SEGMENT_HALF_HALF = 4,
	/// <summary>The indication spins, showing two different colors.</summary>
	SEGMENT_HALF_HALF_ROTATE = 5,
	/// <summary>A single colored spot travels around the segment, with another color as the background.</summary>
	SEGMENT_CHASE = 6,
	/// <summary>Indication gradually changes from off to bright and back to off again, repeatedly.</summary>
	SEGMENT_INTENSITY_SWEEP = 7
};

/// <summary>The brightness of indication.</summary>
enum Intensity
{
	INTENSITY_HIGH = 0,
	INTENSITY_LOW = 1,
	INTENSITY_MEDIUM = 2,
	INTENSITY_OFF = 3,
	/// <summary>Used with <c>SetCustomIntensity</c>.</summary>
	INTENSITY_CUSTOM = 4
};

/// <summary>For dynamic animations, the pace that the animation progresses.</summary>
/// <remarks>Applicable to <see cref="SegmentAnimation::SEGMENT_FLASH"/>, <see cref="SegmentAnimation::SEGMENT_TWO_COLOR_FLASH"/>, <see cref="SegmentAnimation::SEGMENT_HALF_HALF_ROTATE"/>, <see cref="SegmentAnimation::SEGMENT_CHASE"/>, and <see cref="SegmentAnimation::SEGMENT_INTENSITY_SWEEP"/></remarks>
enum Speed
{
	SPEED_STANDARD = 0,
	SPEED_FAST = 1,
	SPEED_SLOW = 2,
	/// <summary>Used with SetCustomSpeed.</summary>
	SPEED_CUSTOM = 3
};

/// <summary>For flashing animations, the manner in which the flashing happens.</summary>
/// <remarks>Applicable to <see cref="SegmentAnimation::SEGMENT_FLASH"/> and <see cref="SegmentAnimation::SEGMENT_TWO_COLOR_FLASH"/>.</remarks>
enum FlashPattern
{
	FLASH_NORMAL = 0,
	FLASH_STROBE = 1,
	FLASH_THREE_PULSE = 2,
	FLASH_SOS = 3,
	FLASH_RANDOM = 4
};

/// <summary>For dynamic animations, the direction that the animation progresses.</summary>
/// <remarks>Mostly for <see cref="SegmentAnimation::SEGMENT_HALF_HALF_ROTATE"/> and <see cref="SegmentAnimation::SEGMENT_CHASE"/>, but also has an effect on the other dynamic animations.</remarks>
enum RotationalDirection
{
	DIRECTION_COUNTERCLOCKWISE = 0,
	DIRECTION_CLOCKWISE = 1
};

/// <summary>Indicates the pattern of sound that will come out of the audible segment (if present).</summary>
enum Audible
{
	AUDIBLE_OFF = 0,
	AUDIBLE_STEADY = 1,
	AUDIBLE_PULSED = 2,
	AUDIBLE_SOS = 3
};

/// <summary>Describes result of a communication attempt with the device.</summary>
enum CommReturnValue
{
	/// <summary>Communication accepted.</summary>
	SUCCESS = 0,
	/// <summary>Requested port was not found.</summary>
	FAILED_PORT_NOT_FOUND = -1,
	/// <summary>Port exists, but unable to open.  May already be in use.</summary>
	FAILED_PORT_OPEN = -2,
	/// <summary>Problem writing to the device.</summary>
	FAILED_WRITE = -3,
	/// <summary>Problem reading from the device.</summary>
	FAILED_READ = -4,
	/// <summary>Response from device has an unexpected checksum, indicating the data may be corrupt.</summary>
	FAILED_CHECKSUM = -5,
	/// <summary>The device declined the command.  Possible value out of range.</summary>
	FAIL_WITH_NACK = -6,
	/// <summary>Communication has not been initialized.  Call <see cref="Init"/> or <see cref="InitByPort"/>.</summary>
	FAILED_NO_INIT = -7,
};

/// <summary>Change indication of a single segment.</summary>
/// <param name="segment">The 0-based index of the segment to change (0-9).</param>
/// <param name="animation">The style of indication to use.</param>
/// <param name="color1">The main color of the indication.</param>
/// <param name="intensity1">The intensity of the main color.</param>
/// <param name="speed">The speed of the indication.  Not applicable to <see cref="SegmentAnimation::SEGMENT_OFF"/>, <see cref="SegmentAnimation::SEGMENT_STEADY"/>, or <see cref="SegmentAnimation::SEGMENT_HALF_HALF"/>.</param>
/// <param name="flashPattern">The manner in which flashing will happen.  Only applicable to <see cref="SegmentAnimation::SEGMENT_FLASH"/> and <see cref="SegmentAnimation::SEGMENT_TWO_COLOR_FLASH"/>.</param>
/// <param name="color2">The second color of the indication.  Not applicable to <see cref="SegmentAnimation::SEGMENT_OFF"/>, <see cref="SegmentAnimation::SEGMENT_STEADY"/>, <see cref="SegmentAnimation::SEGMENT_FLASH"/>, or <see cref="SegmentAnimation::SEGMENT_INTENSITY_SWEEP"/>.</param>
/// <param name="intensity2">The intensity of the second color.  Not applicable to <see cref="SegmentAnimation::SEGMENT_OFF"/>, <see cref="SegmentAnimation::SEGMENT_STEADY"/>, <see cref="SegmentAnimation::SEGMENT_FLASH"/>, or <see cref="SegmentAnimation::SEGMENT_INTENSITY_SWEEP"/>.</param>
/// <param name="direction">The direction that the animation progresses.  Only applicable <see cref="SegmentAnimation::SEGMENT_HALF_HALF_ROTATE"/>, <see cref="SegmentAnimation::SEGMENT_CHASE"/>, and <see cref="SegmentAnimation::SEGMENT_INTENSITY_SWEEP"/>.</param>
/// <returns>The status of the command.</returns>
/// <remarks>This setting is not persisted across power cycles.</remarks>
__declspec(dllimport) enum CommReturnValue SetSegment(int segment, enum SegmentAnimation animation, enum Color color1, enum Intensity intensity1, enum Speed speed, enum FlashPattern flashPattern, enum Color color2, enum Intensity intensity2, enum RotationalDirection direction);

/// <summary>Change the state of the audible segment (if present).</summary>
/// <param name="audible">The manner in which the audible segment is producing sound.</param>
/// <returns>The status of the command.</returns>
/// <remarks>This setting is not persisted across power cycles.</remarks>
__declspec(dllimport) enum CommReturnValue SetAudible(enum Audible audible);

/// <summary>Change the value used when <see cref="Color::CUSTOM_COLOR_1"/> is active.
/// This only controls the ratio of the colors; the intensity of indication (brightness) is controlled separately.</summary>
/// <param name="red">The proportion of red in the custom color.</param>
/// <param name="green">The proportion of green in the custom color.</param>
/// <param name="blue">The proportion of blue in the custom color.</param>
/// <returns>The status of the command.</returns>
/// <remarks>This setting is persisted across power cycles.</remarks>
__declspec(dllimport) enum CommReturnValue SetCustomColor1(unsigned char red, unsigned char green, unsigned char blue);

/// <summary>Change the value used when <see cref="Color::CUSTOM_COLOR_2"/> is active.
/// This only controls the ratio of the colors; the intensity of indication (brightness) is controlled separately.</summary>
/// <param name="red">The proportion of red in the custom color.</param>
/// <param name="green">The proportion of green in the custom color.</param>
/// <param name="blue">The proportion of blue in the custom color.</param>
/// <returns>The status of the command.</returns>
/// <remarks>This setting is persisted across power cycles.</remarks>
__declspec(dllimport) enum CommReturnValue SetCustomColor2(unsigned char red, unsigned char green, unsigned char blue);

/// <summary>Change the value used when <see cref="Intensity::INTENSITY_CUSTOM"/> is active.</summary>
/// <param name="percent">The duty cycle used, 0-100.</param>
/// <returns>The status of the command.</returns>
/// <remarks>Note, perceived brightness is approximately logarithmic with respect to duty cycle, i.e. as percent increases, perceived brightness increases less and less.</remarks>
/// <remarks>This setting is persisted across power cycles.</remarks>
__declspec(dllimport) enum CommReturnValue SetCustomIntensity(int percent);

/// <summary>Change the value used when <see cref="Speed::SPEED_CUSTOM"/> is active.</summary>
/// <param name="dHz">The speed in dHz, 5-200.</param>
/// <returns>The status of the command.</returns>
/// <remarks>This setting is persisted across power cycles.</remarks>
__declspec(dllimport) enum CommReturnValue SetCustomSpeed(int dHz);

/// <summary>Allows turning an individual segment on with a variety of animations.</summary>
/// <param name="segment">The number of the segment on the tower light that you want to configure.  Starting from 0.  For single segment tower lights, 0 is the value to use.</param>
/// <param name="data">An array of three bytes, whose bits mean the following (in order):<br/>
/// Offset:  0; Bit size: 4; Value type: <see cref="Color"/>.                Meaning: Color 1.<br/>
/// Offset:  4; Bit size: 3; Value type: <see cref="Intensity"/>.            Meaning: Intensity 1.<br/>
/// Offset:  7; Bit size: 1; Value type: 0.                                  Meaning: Reserved.<br/>
/// Offset:  8; Bit size: 3; Value type: <see cref="SegmentAnimation"/>.     Meaning: Animation.<br/>
/// Offset: 11; Bit size: 2; Value type: <see cref="Speed"/>.                Meaning: Speed.<br/>
/// Offset: 13; Bit size: 3; Value type: <see cref="FlashPattern"/>.         Meaning: Pattern.<br/>
/// Offset: 16; Bit size: 4; Value type: <see cref="Color"/>.                Meaning: Color 2.<br/>
/// Offset: 20; Bit size: 3; Value type: <see cref="Intensity"/>             Meaning: Intensity 2.<br/>
/// Offset: 23; Bit size: 1; Value type: <see cref="RotationalDirection"/>.  Meaning: Rotation direction.
/// </param>
/// <returns>The status of the command.</returns>
/// <remarks>Same functionality as <see cref="SetSegment"/>, but uses a byte buffer instead of individual arguments.</remarks>
__declspec(dllimport) int SetSegmentAdvanced(int segment, char* data);

#ifdef __cplusplus 
}
#endif
