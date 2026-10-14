// Kiln probe for Unity 6 test scenes (acceptance skill). Records state every FixedUpdate (or every
// LateUpdate for animated bones) and frame timing every Update to JSON Lines ("kiln-probe/1"),
// numbers in invariant culture. It only reads: it never changes gameplay state.
//
// Install once (builder role, any path under a runtime assembly):
//   Assets/_Project/Scripts/Runtime/Kiln/KilnProbe.cs
// Use: a "_KilnProbe" GameObject with this component in a test scene (manage_gameobject create +
// manage_components add, then manage_scene save), or KilnProbe.Attach() in Play mode from an
// execute_code probe. Output: <project>/production/captures/<task>/probe_<run>.jsonl in the
// editor; <persistentDataPath>/Kiln/Probes/<task>/ in a Development player. Analyse with
// analyze.py from the acceptance skill.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Kiln.Probes
{
    /// <summary>
    /// Exposes values to the probe (part HP, ammo, state flags). Compiled in every build so
    /// gameplay components can implement it; implementations only read.
    /// </summary>
    public interface IKilnProbeSource
    {
        /// <summary>Adds this sample's values; each key becomes channel "label.key".</summary>
        void CollectProbeValues(IDictionary<string, float> values);
    }

    [Flags]
    public enum KilnChannels
    {
        None = 0,
        Position = 1,
        Velocity = 2,
        Rotation = 4,
        AngularVelocity = 8,
    }

    public enum KilnSampleTiming
    {
        /// <summary>Every physics step, after gameplay FixedUpdate, before the step's simulation.</summary>
        FixedUpdate,
        /// <summary>Every rendered frame, after animation and IK (bones, Update-driven movers).</summary>
        LateUpdate,
    }

#if UNITY_EDITOR || DEVELOPMENT_BUILD
    [Serializable]
    public sealed class KilnProbeTarget
    {
        [Tooltip("Channel prefix; empty = object name.")] public string label;
        public Transform target;
        public KilnChannels channels = KilnChannels.Position | KilnChannels.Velocity;
    }

    [Serializable]
    public sealed class KilnProbeMember
    {
        public string label;
        public Component component;
        [Tooltip("Field or property: number, bool, enum, string, Vector2/3/4, Quaternion.")]
        public string member;
    }

    [Serializable]
    public sealed class KilnProbeSourceRef
    {
        public string label;
        [Tooltip("A component implementing IKilnProbeSource.")] public MonoBehaviour source;
    }

    [AddComponentMenu("Kiln/Kiln Probe")]
    [DefaultExecutionOrder(10000)]
    [DisallowMultipleComponent]
    public sealed class KilnProbe : MonoBehaviour
    {
        const string Format = "kiln-probe/1";
        const int FlushEvery = 60;

        [Header("Run")]
        [SerializeField] private string task = "probe";
        [SerializeField] private bool startOnPlay;
        [SerializeField, Min(0), Tooltip("Stop after this many samples; 0 = until StopRecording.")]
        private int sampleLimit;
        [SerializeField] private KilnSampleTiming sampleTiming = KilnSampleTiming.FixedUpdate;
        [SerializeField] private bool recordFrames = true;

        [Header("Channels")]
        [SerializeField] private List<KilnProbeTarget> targets = new List<KilnProbeTarget>();
        [SerializeField] private List<KilnProbeMember> members = new List<KilnProbeMember>();
        [SerializeField] private List<KilnProbeSourceRef> sources = new List<KilnProbeSourceRef>();

        static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        readonly List<(string label, IKilnProbeSource source)> runtimeSources = new();
        readonly List<(string label, Func<float> getter)> getters = new();
        readonly List<BoundTarget> boundTargets = new();
        readonly List<BoundMember> boundMembers = new();
        readonly List<(string label, IKilnProbeSource source)> boundSources = new();
        readonly Dictionary<string, float> sourceValues = new();
        readonly FrameTiming[] timing = new FrameTiming[1];
        readonly StringBuilder line = new StringBuilder(1024);

        StreamWriter writer;
        int sampleIndex;
        int unflushed;
        double startTime;

        public bool IsRecording => writer != null;
        public bool Done { get; private set; }
        public string OutputPath { get; private set; }
        public int SamplesWritten { get; private set; }
        public int FramesWritten { get; private set; }

        /// <summary>The probe in the loaded scenes, or null.</summary>
        public static KilnProbe Find() => FindFirstObjectByType<KilnProbe>();

        /// <summary>Play mode only: the scene's probe, or a throwaway one discarded when play stops.</summary>
        public static KilnProbe Attach()
        {
            if (!Application.isPlaying)
                throw new InvalidOperationException("KilnProbe.Attach works in Play mode only; " +
                    "add the component to the test scene through the editor MCP instead.");
            var probe = Find();
            if (probe != null) return probe;
            var go = new GameObject("_KilnProbe"); // kiln:runtime-node play-mode test probe, never saved
            return go.AddComponent<KilnProbe>();
        }

        public KilnProbe AddTarget(string label, Transform target,
            KilnChannels channels = KilnChannels.Position | KilnChannels.Velocity)
        {
            targets.Add(new KilnProbeTarget { label = label, target = target, channels = channels });
            return this;
        }

        public KilnProbe AddMember(string label, Component component, string member)
        {
            members.Add(new KilnProbeMember { label = label, component = component, member = member });
            return this;
        }

        public KilnProbe AddSource(string label, IKilnProbeSource source)
        {
            runtimeSources.Add((label, source));
            return this;
        }

        /// <summary>Any read-only getter, e.g. () => hero.velocity.magnitude.</summary>
        public KilnProbe AddValue(string label, Func<float> getter)
        {
            getters.Add((label, getter));
            return this;
        }

        public KilnProbe SetTiming(KilnSampleTiming timingMode)
        {
            sampleTiming = timingMode;
            return this;
        }

        /// <summary>Starts a new file; returns its absolute path. samples &lt; 0 keeps the inspector limit.</summary>
        public string StartRecording(string taskName = null, string runName = null, int samples = -1)
        {
            if (IsRecording) StopRecording();
            if (!string.IsNullOrEmpty(taskName)) task = taskName;
            if (samples >= 0) sampleLimit = samples;
            string run = string.IsNullOrEmpty(runName)
                ? DateTime.UtcNow.ToString("yyyyMMdd-HHmmss", Inv) : runName;
            OutputPath = Path.Combine(OutputRoot(), Safe(task), "probe_" + Safe(run) + ".jsonl");
            Directory.CreateDirectory(Path.GetDirectoryName(OutputPath));
            Bind();
            writer = new StreamWriter(OutputPath, false, new UTF8Encoding(false));
            sampleIndex = 0;
            unflushed = 0;
            SamplesWritten = 0;
            FramesWritten = 0;
            Done = false;
            startTime = Now();
            WriteHeader(run);
            return OutputPath;
        }

        /// <summary>Closes the file; returns its path (null when nothing was recording).</summary>
        public string StopRecording()
        {
            if (writer == null) return OutputPath;
            line.Clear();
            line.Append("{\"type\":\"end\",\"samples\":").Append(SamplesWritten.ToString(Inv))
                .Append(",\"frames\":").Append(FramesWritten.ToString(Inv)).Append('}');
            Emit();
            writer.Flush();
            writer.Dispose();
            writer = null;
            Done = true;
            return OutputPath;
        }

        void Start()
        {
            if (startOnPlay && !IsRecording) StartRecording();
        }

        void FixedUpdate()
        {
            if (IsRecording && sampleTiming == KilnSampleTiming.FixedUpdate) Sample();
        }

        void LateUpdate()
        {
            if (IsRecording && sampleTiming == KilnSampleTiming.LateUpdate) Sample();
        }

        void Update()
        {
            if (!IsRecording || !recordFrames) return;
            // FrameTimingManager is always active in the editor and Development players; its
            // values describe the frame four frames back.
            FrameTimingManager.CaptureFrameTimings();
            uint count = FrameTimingManager.GetLatestTimings(1, timing);
            line.Clear();
            line.Append("{\"type\":\"frame\",\"frame\":").Append(Time.frameCount.ToString(Inv))
                .Append(",\"sample\":").Append(sampleIndex.ToString(Inv));
            Key("dt_ms"); Num(Time.unscaledDeltaTime * 1000.0);
            if (count > 0)
            {
                Key("cpu_ms"); Num((double)timing[0].cpuFrameTime);
                Key("main_ms"); Num((double)timing[0].cpuMainThreadFrameTime);
                Key("render_ms"); Num((double)timing[0].cpuRenderThreadFrameTime);
                Key("gpu_ms"); Num((double)timing[0].gpuFrameTime);
            }
            line.Append('}');
            Emit();
            FramesWritten++;
        }

        void OnDisable() => StopRecording();

        void OnApplicationQuit() => StopRecording();

        void Sample()
        {
            sampleIndex++;
            line.Clear();
            line.Append("{\"type\":\"tick\",\"tick\":").Append(sampleIndex.ToString(Inv));
            Key("t"); Num(Now() - startTime);
            foreach (var t in boundTargets) WriteTarget(t);
            foreach (var m in boundMembers)
            {
                Key(m.Label);
                try { Value(m.Read()); } catch (Exception) { line.Append("null"); }
            }
            foreach (var (label, source) in boundSources)
            {
                sourceValues.Clear();
                try { source.CollectProbeValues(sourceValues); } catch (Exception) { continue; }
                foreach (var kv in sourceValues)
                {
                    Key(label + "." + kv.Key);
                    Num(kv.Value);
                }
            }
            foreach (var (label, getter) in getters)
            {
                Key(label);
                try { Num(getter()); } catch (Exception) { line.Append("null"); }
            }
            line.Append('}');
            Emit();
            SamplesWritten++;
            if (sampleLimit > 0 && SamplesWritten >= sampleLimit) StopRecording();
        }

        double Now() => sampleTiming == KilnSampleTiming.FixedUpdate
            ? Time.fixedTimeAsDouble : Time.timeAsDouble;

        void Bind()
        {
            boundTargets.Clear();
            foreach (var t in targets)
                if (t != null && t.target != null) boundTargets.Add(new BoundTarget(t));
            boundMembers.Clear();
            foreach (var m in members)
            {
                var bound = m == null ? null : BoundMember.Create(m);
                if (bound != null) boundMembers.Add(bound);
                else if (m != null) Debug.LogWarning($"KilnProbe: no readable member '{m.member}' on {m.component}");
            }
            boundSources.Clear();
            foreach (var s in sources)
            {
                if (s?.source is IKilnProbeSource src)
                    boundSources.Add((string.IsNullOrEmpty(s.label) ? s.source.name : s.label, src));
                else if (s?.source != null)
                    Debug.LogWarning($"KilnProbe: {s.source} does not implement IKilnProbeSource");
            }
            boundSources.AddRange(runtimeSources);
        }

        void WriteHeader(string run)
        {
            line.Clear();
            line.Append("{\"type\":\"header\",\"format\":\"").Append(Format).Append('"');
            Key("engine"); Str("unity");
            Key("engine_version"); Str(Application.unityVersion);
            Key("task"); Str(task);
            Key("run"); Str(run);
            Key("scene"); Str(SceneManager.GetActiveScene().path);
            Key("sample"); Str(sampleTiming == KilnSampleTiming.FixedUpdate ? "fixed_update" : "late_update");
            Key("physics_hz"); Num(1.0 / Time.fixedDeltaTime);
            Key("units_per_meter"); Num(1.0);
            Key("up"); Str("y");
            Key("time_scale"); Num(Time.timeScale);
            Key("target_frame_rate"); line.Append(Application.targetFrameRate.ToString(Inv));
            Key("vsync_count"); line.Append(QualitySettings.vSyncCount.ToString(Inv));
            Key("editor"); line.Append(Application.isEditor ? "true" : "false");
            Key("timing_lag_frames"); line.Append('4');
            Key("started_utc"); Str(DateTime.UtcNow.ToString("o", Inv));
            line.Append('}');
            Emit();
        }

        void WriteTarget(BoundTarget b)
        {
            if (b.Transform == null) return;
            var ch = b.Channels;
            if ((ch & KilnChannels.Position) != 0)
            {
                Key(b.Label + ".pos");
                if (b.Body != null) Vec(b.Body.position);
                else if (b.Body2D != null) Vec((Vector3)b.Body2D.position);
                else Vec(b.Transform.position);
            }
            if ((ch & KilnChannels.Velocity) != 0)
            {
                if (b.Body != null) { Key(b.Label + ".vel"); Vec(b.Body.linearVelocity); }
                else if (b.Body2D != null) { Key(b.Label + ".vel"); Vec((Vector3)b.Body2D.linearVelocity); }
                else if (b.Controller != null) { Key(b.Label + ".vel"); Vec(b.Controller.velocity); }
            }
            if ((ch & KilnChannels.Rotation) != 0)
            {
                Key(b.Label + ".rot");
                Quat(b.Body != null ? b.Body.rotation : b.Transform.rotation);
            }
            if ((ch & KilnChannels.AngularVelocity) != 0 && b.Body != null)
            {
                Key(b.Label + ".angvel");
                Vec(b.Body.angularVelocity);
            }
        }

        void Emit()
        {
            line.Append('\n');
            writer.Write(line.ToString());
            if (++unflushed >= FlushEvery)
            {
                writer.Flush();
                unflushed = 0;
            }
        }

        void Key(string key)
        {
            line.Append(',');
            Str(key);
            line.Append(':');
        }

        void Str(string s)
        {
            line.Append('"');
            foreach (char c in s ?? string.Empty)
            {
                switch (c)
                {
                    case '"': line.Append("\\\""); break;
                    case '\\': line.Append("\\\\"); break;
                    case '\n': line.Append("\\n"); break;
                    case '\r': line.Append("\\r"); break;
                    case '\t': line.Append("\\t"); break;
                    default:
                        if (c < ' ') line.Append("\\u").Append(((int)c).ToString("x4", Inv));
                        else line.Append(c);
                        break;
                }
            }
            line.Append('"');
        }

        void Num(double v)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) line.Append("null");
            else line.Append(v.ToString("R", Inv));
        }

        void Num(float v)
        {
            if (float.IsNaN(v) || float.IsInfinity(v)) line.Append("null");
            else line.Append(v.ToString("R", Inv));
        }

        void Vec(Vector3 v)
        {
            line.Append('['); Num(v.x); line.Append(','); Num(v.y); line.Append(','); Num(v.z); line.Append(']');
        }

        void Quat(Quaternion q)
        {
            line.Append('['); Num(q.x); line.Append(','); Num(q.y); line.Append(',');
            Num(q.z); line.Append(','); Num(q.w); line.Append(']');
        }

        void Value(object v)
        {
            switch (v)
            {
                case null: line.Append("null"); break;
                case bool b: line.Append(b ? "true" : "false"); break;
                case float f: Num(f); break;
                case double d: Num(d); break;
                case int or long or short or byte or uint or ulong or ushort or sbyte:
                    line.Append(Convert.ToString(v, Inv)); break;
                case Vector2 v2: Vec(v2); break;
                case Vector3 v3: Vec(v3); break;
                case Vector4 v4:
                    line.Append('['); Num(v4.x); line.Append(','); Num(v4.y); line.Append(',');
                    Num(v4.z); line.Append(','); Num(v4.w); line.Append(']'); break;
                case Quaternion q: Quat(q); break;
                case Enum e: Str(e.ToString()); break;
                case string s: Str(s); break;
                case UnityEngine.Object o: Str(o != null ? o.name : null); break;
                default: Str(Convert.ToString(v, Inv)); break;
            }
        }

        static string OutputRoot()
        {
#if UNITY_EDITOR
            return Path.GetFullPath(Path.Combine(Application.dataPath, "..", "production", "captures"));
#else
            return Path.Combine(Application.persistentDataPath, "Kiln", "Probes");
#endif
        }

        static string Safe(string name)
        {
            var sb = new StringBuilder(name.Length);
            foreach (char c in name)
                sb.Append(char.IsLetterOrDigit(c) || c == '-' || c == '_' || c == '.' ? c : '_');
            return sb.Length > 0 ? sb.ToString() : "probe";
        }

        sealed class BoundTarget
        {
            public readonly string Label;
            public readonly Transform Transform;
            public readonly Rigidbody Body;
            public readonly Rigidbody2D Body2D;
            public readonly CharacterController Controller;
            public readonly KilnChannels Channels;

            public BoundTarget(KilnProbeTarget t)
            {
                Transform = t.target;
                Label = string.IsNullOrEmpty(t.label) ? t.target.name : t.label;
                Body = t.target.GetComponent<Rigidbody>();
                Body2D = t.target.GetComponent<Rigidbody2D>();
                Controller = t.target.GetComponent<CharacterController>();
                Channels = t.channels;
            }
        }

        sealed class BoundMember
        {
            const BindingFlags Flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            public string Label { get; private set; }
            Component component;
            FieldInfo field;
            PropertyInfo property;

            public static BoundMember Create(KilnProbeMember m)
            {
                if (m.component == null || string.IsNullOrEmpty(m.member)) return null;
                var type = m.component.GetType();
                var b = new BoundMember
                {
                    Label = string.IsNullOrEmpty(m.label) ? m.component.name + "." + m.member : m.label,
                    component = m.component,
                    property = type.GetProperty(m.member, Flags),
                };
                if (b.property == null || !b.property.CanRead || b.property.GetIndexParameters().Length > 0)
                {
                    b.property = null;
                    b.field = type.GetField(m.member, Flags);
                }
                return b.property != null || b.field != null ? b : null;
            }

            public object Read() => component == null ? null
                : field != null ? field.GetValue(component) : property.GetValue(component);
        }
    }
#endif
}
