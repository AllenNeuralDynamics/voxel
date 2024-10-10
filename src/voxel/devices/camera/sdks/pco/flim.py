# -*- coding: utf-8 -*-
"""
This module extends the functionality of pco.Camera for support of pco.flim.

Copyright @ Excelitas PCO GmbH 2005-2023
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class Flim:

    def __init__(self, phase_number, phase_symmetry, phase_order, tap_select,
                 asymmetry_correction, output_mode=None, frequency=None,
                 source_select=None, output_waveform=None):
        """
        """
        logger.debug("")

        self.config(phase_number,
                    phase_symmetry,
                    phase_order,
                    tap_select,
                    asymmetry_correction,
                    output_mode,
                    frequency,
                    source_select,
                    output_waveform)

    def __enter__(self):
        """
        __enter__ method implements the context manager for futur use.

        >>> with pco.Flim() as fc:
        ...:   # do some stuff
        """
        logger.debug("")
        return self

    def __exit__(self, type, value, traceback):
        """
        __exit__ method implements the context manager for futur use.

        >>> with pco.Flim() as fc:
        ...:   # do some stuff
        """
        logger.debug("")
        pass

    def config(self, phase_number, phase_symmetry, phase_order, tap_select,
               asymmetry_correction, output_mode=None, frequency=None,
               source_select=None, output_waveform=None):
        """Configure the Flim class with needed parameter.

        """
        logger.debug("")

        self.phase_number = phase_number
        self.phase_symmetry = phase_symmetry
        self.phase_order = phase_order
        self.tap_select = tap_select
        self.asymmetry_correction = asymmetry_correction

    def calculate(self, list_of_images):
        """Calculates the image stack and returns phi, m, ni and phasor.

        >>> phi, m, ni, phasor = calculate(list_of_images)
        """
        logger.debug("")

        stack = self.get_stack(list_of_images)

        phasor, ni = self.numeric_harmonic_analysis_phasor(
            stack,
            self.phase_number,
            self.phase_symmetry,
            self.phase_order,
            self.tap_select,
            self.asymmetry_correction)

        phi = self.get_phase(phasor)
        m = self.get_magnitude(phasor)

        return phi, m, ni, phasor

    def numeric_harmonic_analysis_phasor(self, stack, phase_number,
                                         phase_symmetry, phase_order,
                                         tap_select, asymmetry_correction):
        """
        """
        logger.debug("")

        w = self.get_index(
            phase_number,
            phase_symmetry,
            phase_order,
            tap_select,
            asymmetry_correction)

        dict_phases = {
            'manual shifting': 2,
            '2 phases': 2,
            '4 phases': 4,
            '8 phases': 8,
            '16 phases': 16}

        z = np.einsum('ijk,k->ij', stack, w)

        b = stack.mean(axis=2)

        phasor = (2.0 / (b * dict_phases[phase_number] + np.finfo(float).eps)) * z
        bits = 14
        ni = b / ((2**bits) - 1)

        return phasor, ni

    # -------------------------------------------------------------------------
    def get_stack(self, list_of_images):
        """Returns the image stack."""
        logger.debug("")
        return np.stack(list_of_images, axis=2)

    # -------------------------------------------------------------------------
    def get_phase(self, phasor):
        """Returns the phase."""
        logger.debug("")
        return np.arctan2(phasor.imag, phasor.real)

    # -------------------------------------------------------------------------
    def get_magnitude(self, phasor):
        """Returns the magnitude."""
        logger.debug("")
        return np.abs(phasor)

    # -------------------------------------------------------------------------
    def get_index(
        self,
        phase_number,
        phase_symmetry,
        phase_order,
        tap_select,
        asymmetry_correction
    ):
        """Returns the multiplier depending of the configuration."""
        logger.debug("")

        phase_number_to_int = {
            'manual shifting': 2,
            '2 phases': 2,
            '4 phases': 4,
            '8 phases': 8,
            '16 phases': 16}
        w = np.exp(-1j * 2.0 * np.pi * np.arange(phase_number_to_int[phase_number]) / phase_number_to_int[phase_number])

        n = phase_number
        s = phase_symmetry
        o = phase_order
        t = tap_select
        c = asymmetry_correction

        if n == 'manual shifting' and t == 'both':
            return [w[0],     w[1]]
        elif n == 'manual shifting' and t == 'tap A':
            return [w[0]]
        elif n == 'manual shifting' and t == 'tap B':
            return [w[1]]
        elif n == '2 phases' and s == 'singular' and t == 'both':
            return [w[0],     w[1]]
        elif n == '2 phases' and s == 'singular' and t == 'tap A':
            return [w[0]]
        elif n == '2 phases' and s == 'singular' and t == 'tap B':
            return [w[1]]
        elif n == '2 phases' and s == 'twice' and t == 'both':
            return [0.5*w[0], 0.5*w[1], 0.5*w[1], 0.5*w[0]]
        elif n == '2 phases' and s == 'twice' and t == 'tap A':
            return [w[0],     w[1]]
        elif n == '2 phases' and s == 'twice' and t == 'tap B':
            return [w[1],     w[0]]
        elif n == '2 phases' and s == 'twice' and o == 'opposite' and t == 'both' and c == 'average':
            return [w[0],     w[1]]
        elif n == '4 phases' and s == 'singular' and t == 'both' and c == 'off':
            return [w[0],     w[2],     w[1],     w[3]]
        elif n == '4 phases' and s == 'singular' and t == 'tap A' and c == 'off':
            return [w[0],     w[1]]
        elif n == '4 phases' and s == 'singular' and t == 'tap B' and c == 'off':
            return [w[2],     w[3]]
        elif n == '4 phases' and s == 'twice' and o == 'ascending' and t == 'both' and c == 'off':
            return [0.5*w[0], 0.5*w[2], 0.5*w[1], 0.5*w[3], 0.5*w[2], 0.5*w[0], 0.5*w[3], 0.5*w[1]]
        elif n == '4 phases' and s == 'twice' and o == 'ascending' and t == 'tap A' and c == 'off':
            return [w[0],     w[1],     w[2],     w[3]]
        elif n == '4 phases' and s == 'twice' and o == 'ascending' and t == 'tap B' and c == 'off':
            return [w[2],     w[3],     w[0],     w[0]]
        elif n == '4 phases' and s == 'twice' and o == 'opposite' and t == 'both' and c == 'off':
            return [0.5*w[0], 0.5*w[2], 0.5*w[2], 0.5*w[0], 0.5*w[1], 0.5*w[3], 0.5*w[3], 0.5*w[1]]
        elif n == '4 phases' and s == 'twice' and o == 'opposite' and t == 'both' and c == 'average':
            return [w[0],     w[2],     w[1],     w[3]]
        elif n == '4 phases' and s == 'twice' and o == 'opposite' and t == 'tap A' and c == 'off':
            return [w[0],     w[2],     w[1],     w[3]]
        elif n == '4 phases' and s == 'twice' and o == 'opposite' and t == 'tap B' and c == 'off':
            return [w[2],     w[0],     w[3],     w[1]]
        elif n == '8 phases' and s == 'singular' and t == 'both' and c == 'off':
            return [w[0],     w[4],     w[1],     w[5],     w[2],     w[6],     w[3],     w[7]]
        elif n == '8 phases' and s == 'singular' and t == 'tap A' and c == 'off':
            return [w[0],     w[1],     w[2],     w[3]]
        elif n == '8 phases' and s == 'singular' and t == 'tap B' and c == 'off':
            return [w[4],     w[5],     w[6],     w[7]]
        elif n == '8 phases' and s == 'twice' and o == 'ascending' and t == 'both' and c == 'off':
            return [0.5*w[0], 0.5*w[4], 0.5*w[1], 0.5*w[5], 0.5*w[2], 0.5*w[6], 0.5*w[3], 0.5*w[7],
                    0.5*w[4], 0.5*w[0], 0.5*w[5], 0.5*w[1], 0.5*w[6], 0.5*w[2], 0.5*w[7], 0.5*w[3]]
        elif n == '8 phases' and s == 'twice' and o == 'ascending' and t == 'tap A' and c == 'off':
            return [w[0],     w[1],     w[2],     w[3],     w[4],     w[5],     w[6],     w[7]]
        elif n == '8 phases' and s == 'twice' and o == 'ascending' and t == 'tap B' and c == 'off':
            return [w[4],     w[5],     w[6],     w[7],     w[0],     w[1],     w[2],     w[3]]
        elif n == '8 phases' and s == 'twice' and o == 'opposite' and t == 'both' and c == 'off':
            return [0.5*w[0], 0.5*w[4], 0.5*w[4], 0.5*w[0], 0.5*w[1], 0.5*w[5], 0.5*w[5], 0.5*w[1],
                    0.5*w[2], 0.5*w[6], 0.5*w[6], 0.5*w[2], 0.5*w[3], 0.5*w[7], 0.5*w[7], 0.5*w[3]]
        elif n == '8 phases' and s == 'twice' and o == 'opposite' and t == 'both' and c == 'average':
            return [w[0],     w[4],     w[1],     w[5],     w[2],     w[6],     w[3],     w[7]]
        elif n == '8 phases' and s == 'twice' and o == 'opposite' and t == 'tap A' and c == 'off':
            return [w[0],     w[4],     w[1],     w[5],     w[2],     w[6],     w[3],     w[7]]
        elif n == '8 phases' and s == 'twice' and o == 'opposite' and t == 'tap B' and c == 'off':
            return [w[4],     w[0],     w[5],     w[1],     w[6],     w[2],     w[7],     w[3]]
        elif n == '16 phases' and s == 'singular' and t == 'both' and c == 'off':
            return [w[0],     w[8],     w[1],     w[9],     w[2],     w[10],     w[3],     w[11],
                    w[4],     w[12],     w[5],     w[13],     w[6],     w[14],     w[7],     w[15]]
        elif n == '16 phases' and s == 'singular' and t == 'tap A' and c == 'off':
            return [w[0],     w[1],     w[2],     w[3],     w[4],     w[5],     w[6],     w[7]]
        elif n == '16 phases' and s == 'singular' and t == 'tap B' and c == 'off':
            return [w[8],     w[9],     w[0],     w[11],     w[12],     w[13],     w[14],     w[15]]
        elif n == '16 phases' and s == 'twice' and o == 'ascending' and t == 'both' and c == 'off':
            return [0.5*w[0], 0.5*w[8], 0.5*w[1], 0.5*w[9], 0.5*w[2], 0.5*w[10], 0.5*w[3], 0.5*w[11],
                    0.5*w[4], 0.5*w[12], 0.5*w[5], 0.5*w[13], 0.5*w[6], 0.5*w[14], 0.5*w[7], 0.5*w[15],
                    0.5*w[8], 0.5*w[0], 0.5*w[9], 0.5*w[1], 0.5*w[10], 0.5*w[2], 0.5*w[11], 0.5*w[3],
                    0.5*w[12], 0.5*w[4], 0.5*w[3], 0.5*w[5], 0.5*w[14], 0.5*w[6], 0.5*w[15], 0.5*w[7]]
        elif n == '16 phases' and s == 'twice' and o == 'ascending' and t == 'tap A' and c == 'off':
            return [w[0],     w[1],     w[2],     w[3],     w[4],     w[5],     w[6],     w[7],
                    w[8],     w[9],     w[10],     w[11],     w[12],     w[13],     w[14],     w[15]]
        elif n == '16 phases' and s == 'twice' and o == 'ascending' and t == 'tap B' and c == 'off':
            return [w[8],     w[9],     w[10],     w[11],     w[12],     w[13],     w[14],     w[15],
                    w[0],     w[1],     w[2],     w[3],     w[4],     w[5],     w[6],     w[7]]
        elif n == '16 phases' and s == 'twice' and o == 'opposite' and t == 'both' and c == 'off':
            return [0.5*w[0], 0.5*w[8], 0.5*w[8], 0.5*w[0], 0.5*w[1], 0.5*w[9], 0.5*w[9], 0.5*w[1],
                    0.5*w[2], 0.5*w[10], 0.5*w[10], 0.5*w[2], 0.5*w[3], 0.5*w[11], 0.5*w[11], 0.5*w[3],
                    0.5*w[4], 0.5*w[12], 0.5*w[12], 0.5*w[4], 0.5*w[5], 0.5*w[13], 0.5*w[13], 0.5*w[5],
                    0.5*w[6], 0.5*w[14], 0.5*w[14], 0.5*w[6], 0.5*w[7], 0.5*w[15], 0.5*w[15], 0.5*w[7]]
        elif n == '16 phases' and s == 'twice' and o == 'opposite' and t == 'both' and c == 'average':
            return [w[0],     w[8],     w[1],     w[9],     w[2],     w[10],     w[3],     w[11],
                    w[4],     w[12],     w[5],     w[13],     w[6],     w[14],     w[7],     w[15]]
        elif n == '16 phases' and s == 'twice' and o == 'opposite' and t == 'tap A' and c == 'off':
            return [w[0],     w[8],     w[1],     w[9],     w[2],     w[10],     w[3],     w[11],
                    w[4],     w[12],     w[5],     w[13],     w[6],     w[14],     w[7],     w[15]]
        elif n == '16 phases' and s == 'twice' and o == 'opposite' and t == 'tap B' and c == 'off':
            return [w[8],     w[0],     w[9],     w[1],     w[10],     w[2],     w[11],     w[3],
                    w[12],     w[4],     w[13],     w[5],     w[14],     w[6],     w[15],     w[7]]

        else:
            return None
