private AudioEffectRecord _effect;
private AudioStreamSample _recording;

public override void _Ready()
{
    // We get the index of the "Record" bus.
    int idx = AudioServer.GetBusIndex("Record");
    // And use it to retrieve its first effect, which has been defined
    // as an "AudioEffectRecord" resource.
    _effect = (AudioEffectRecord)AudioServer.GetBusEffect(idx, 0);
}