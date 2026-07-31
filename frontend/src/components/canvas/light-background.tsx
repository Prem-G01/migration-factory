/** Static CSS equivalent of GalaxyBackground for light theme — a
 * starfield reads as a bug (or a bizarre choice) on a white background,
 * so light mode gets a soft gradient-mesh wash instead. No canvas / no
 * animation loop needed since it's just gradients. */
export function LightBackground() {
  return (
    <div className="pointer-events-none fixed inset-0" style={{ zIndex: 0 }} aria-hidden="true">
      <div className="absolute inset-0" style={{ background: "var(--void)" }} />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(600px circle at 12% 15%, rgba(0,145,194,0.10), transparent 60%)," +
            "radial-gradient(700px circle at 88% 75%, rgba(109,40,217,0.08), transparent 60%)," +
            "radial-gradient(500px circle at 60% 5%, rgba(5,150,107,0.06), transparent 60%)",
        }}
      />
    </div>
  );
}
