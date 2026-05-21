/**
 * components/TypingIndicator.tsx
 * -------------------------------
 * PURPOSE:
 *   Animated three-dot "thinking" indicator shown while the LLM is
 *   generating the first token (i.e. after routing completes but before
 *   the first token arrives).
 *
 * CONCEPT — React Native Animated API
 *   React Native's Animated library drives animations on the native thread
 *   (via the "native driver"), bypassing the JS bridge for smooth 60fps.
 *
 *   Key building blocks:
 *     Animated.Value    — a single numeric value that can be animated
 *     Animated.timing() — interpolates a Value from A to B over time
 *     Animated.loop()   — repeats an animation forever
 *     Animated.stagger()— starts a sequence with delays between each item
 *
 *   We create one Animated.Value per dot and stagger their bounce
 *   animations 200ms apart so they don't all move at the same time.
 */

import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { Colors, Shadow } from '../theme';

export default function TypingIndicator() {
  // One animated value per dot — all start at 0.
  const dots = [useRef(new Animated.Value(0)).current,
                useRef(new Animated.Value(0)).current,
                useRef(new Animated.Value(0)).current];

  useEffect(() => {
    // Build a bounce animation for a single dot:
    // 0 → -8px (up) → 0 (down), over 500ms, then hold for 300ms.
    const bounce = (val: Animated.Value) =>
      Animated.sequence([
        Animated.timing(val, { toValue: -8, duration: 300, useNativeDriver: true }),
        Animated.timing(val, { toValue: 0,  duration: 300, useNativeDriver: true }),
        Animated.delay(100),
      ]);

    // Stagger dots 150ms apart, then loop the whole sequence.
    const animation = Animated.loop(
      Animated.stagger(150, dots.map(bounce)),
    );
    animation.start();

    return () => animation.stop();
  }, []);

  return (
    <View style={styles.wrap}>
      {dots.map((anim, i) => (
        <Animated.View
          key={i}
          style={[styles.dot, { transform: [{ translateY: anim }] }]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: '#fff',
    paddingVertical: 14,
    paddingHorizontal: 18,
    borderRadius: 18,
    borderBottomLeftRadius: 4,
    alignSelf: 'flex-start',
    ...Shadow.card,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: Colors.muted,
  },
});
