// Kiln probe component (acceptance skill). Records actor state after physics every frame (or at
// SampleHz) to JSON Lines ("kiln-probe/1") under Saved/Kiln/Probes/<Task>/. It only reads: it never
// changes gameplay state.
//
// Install once (builder role): copy KilnProbeComponent.h/.cpp to Source/<Module>/Kiln/, add
// "RenderCore", "RHI", "Json" to the module's PrivateDependencyModuleNames, restart the editor and
// do a full build (Live Coding cannot add new UCLASS/UPROPERTY members). Then add the component to
// actors in test maps through the Unreal MCP (ActorTools.add_component), set its properties with
// ObjectTools.set_properties and save with SceneTools.save_actor. Start/stop from Blueprint, Python
// or the Kiln toolset (kiln_probe_start / kiln_probe_stop / kiln_probe_read). Units: cm, Z-up.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "KilnProbeComponent.generated.h"

class FJsonObject;
class FJsonValue;

/** Another actor whose transform is sampled. */
USTRUCT(BlueprintType)
struct FKilnProbeActor
{
	GENERATED_BODY()

	/** Channel prefix. Empty uses the actor label. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	FString Label;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	TSoftObjectPtr<AActor> Actor;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	bool bVelocity = true;

	/** Writes [pitch, yaw, roll] in degrees. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	bool bRotation = false;
};

/** A socket or bone whose world location is sampled (feet, muzzles, part attachments). */
USTRUCT(BlueprintType)
struct FKilnProbeSocket
{
	GENERATED_BODY()

	/** Channel name. Empty uses the socket name. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	FString Label;

	/** Actor that holds the mesh. Empty uses the owner. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	TSoftObjectPtr<AActor> Actor;

	/** Component tag or name. None uses the first skeletal mesh, else the root component. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	FName Component;

	/** Socket or bone name. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	FName Socket;
};

/** A property, or a const/pure parameterless UFUNCTION, read every sample (part HP, ammo, state). */
USTRUCT(BlueprintType)
struct FKilnProbeValue
{
	GENERATED_BODY()

	/** Channel name. Empty uses the property name. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	FString Label;

	/** Actor to read. Empty uses the owner. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	TSoftObjectPtr<AActor> Actor;

	/** Component tag or name to read from. None reads the actor itself. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	FName Component;

	/** Property (number, bool, enum, name, string, FVector, FRotator) or getter function name. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln")
	FName Name;
};

/** Records actor state to JSON Lines for Kiln acceptance checks. Read-only. */
UCLASS(ClassGroup = (Kiln), BlueprintType, Blueprintable,
	meta = (BlueprintSpawnableComponent, DisplayName = "Kiln Probe"))
class UKilnProbeComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UKilnProbeComponent();

	/** Folder under Saved/Kiln/Probes. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Run")
	FString Task = TEXT("probe");

	/** Samples per second of game time. 0 samples every frame. Frame timing is written every frame. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Run", meta = (ClampMin = "0", Units = "Hz"))
	float SampleHz = 0.f;

	/** Stop after this many samples. 0 records until StopRecording or EndPlay. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Run", meta = (ClampMin = "0"))
	int32 SampleLimit = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Run")
	bool bStartOnBeginPlay = false;

	/** Owner location, velocity and, for characters, movement mode. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Channels")
	bool bRecordOwner = true;

	/** Frame delta and game/render thread and GPU times per frame. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Channels")
	bool bRecordFrameTiming = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Channels")
	TArray<FKilnProbeActor> Actors;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Channels")
	TArray<FKilnProbeSocket> Sockets;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Kiln|Channels")
	TArray<FKilnProbeValue> Values;

	/**
	 * Starts a new file. Empty arguments keep Task and use a UTC timestamp as the run name.
	 * @return Absolute path of the JSON Lines file.
	 */
	UFUNCTION(BlueprintCallable, Category = "Kiln")
	FString StartRecording(const FString& InTask, const FString& RunName);

	/** Flushes and closes the file. @return Its absolute path, empty if nothing was recorded. */
	UFUNCTION(BlueprintCallable, Category = "Kiln")
	FString StopRecording();

	UFUNCTION(BlueprintPure, Category = "Kiln")
	bool IsRecording() const { return bRecording; }

	UFUNCTION(BlueprintPure, Category = "Kiln")
	FString GetOutputPath() const { return OutputFile; }

	UFUNCTION(BlueprintPure, Category = "Kiln")
	int32 GetSamplesWritten() const { return SampleIndex; }

	virtual void TickComponent(float DeltaTime, ELevelTick TickType,
		FActorComponentTickFunction* ThisTickFunction) override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void WriteHeader(const FString& RunName);
	void WriteChannels(FJsonObject& Line) const;
	void WriteFrameTiming(FJsonObject& Line) const;
	void AppendLine(const TSharedRef<FJsonObject>& Line);
	void Flush();

	FString OutputFile;
	FString Pending;
	bool bRecording = false;
	bool bFileCreated = false;
	int32 SampleIndex = 0;
	int32 FrameCount = 0;
	double StartTime = 0.0;
	double NextSampleTime = 0.0;
	double LastFlush = 0.0;
};
