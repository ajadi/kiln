// Kiln probe component (acceptance skill). See KilnProbeComponent.h for setup.

#include "KilnProbeComponent.h"

#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "CoreGlobals.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "DynamicRHI.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/WorldSettings.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "Misc/DateTime.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "RenderTimer.h" // GGameThreadTime, GRenderThreadTime (RenderCore; RenderCore.h before UE 5.3)
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/UnrealType.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(KilnProbeComponent)

namespace KilnProbe
{
	static TSharedPtr<FJsonValue> Null()
	{
		return MakeShared<FJsonValueNull>();
	}

	/** Non-finite numbers become null so every line stays strict JSON. */
	static TSharedPtr<FJsonValue> Num(double Value)
	{
		if (!FMath::IsFinite(Value))
		{
			return Null();
		}
		return MakeShared<FJsonValueNumber>(Value);
	}

	static TSharedPtr<FJsonValue> Vec(const FVector& V)
	{
		return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{Num(V.X), Num(V.Y), Num(V.Z)});
	}

	static TSharedPtr<FJsonValue> Rot(const FRotator& R)
	{
		return MakeShared<FJsonValueArray>(
			TArray<TSharedPtr<FJsonValue>>{Num(R.Pitch), Num(R.Yaw), Num(R.Roll)});
	}

	static FString LabelOf(const AActor* Actor)
	{
#if WITH_EDITOR
		return Actor->GetActorLabel();
#else
		return Actor->GetName();
#endif
	}

	static FString Safe(const FString& In)
	{
		FString Out = In;
		for (TCHAR& C : Out)
		{
			if (!FChar::IsAlnum(C) && C != TEXT('-') && C != TEXT('_') && C != TEXT('.'))
			{
				C = TEXT('_');
			}
		}
		return Out.IsEmpty() ? FString(TEXT("probe")) : Out;
	}

	static AActor* Resolve(const TSoftObjectPtr<AActor>& Ptr, AActor* Owner)
	{
		return Ptr.IsNull() ? Owner : Ptr.Get();
	}

	static UActorComponent* FindComponent(const AActor* Actor, FName Name)
	{
		TInlineComponentArray<UActorComponent*> Components(Actor);
		for (UActorComponent* Component : Components)
		{
			if (Component && (Component->ComponentHasTag(Name) || Component->GetFName() == Name))
			{
				return Component;
			}
		}
		return nullptr;
	}

	static TSharedPtr<FJsonValue> PropertyValue(const FProperty* Prop, const void* Ptr)
	{
		if (const FBoolProperty* Bool = CastField<FBoolProperty>(Prop))
		{
			return MakeShared<FJsonValueBoolean>(Bool->GetPropertyValue(Ptr));
		}
		if (const FEnumProperty* Enum = CastField<FEnumProperty>(Prop))
		{
			const int64 Value = Enum->GetUnderlyingProperty()->GetSignedIntPropertyValue(Ptr);
			return MakeShared<FJsonValueString>(Enum->GetEnum()->GetNameStringByValue(Value));
		}
		if (const FNumericProperty* Numeric = CastField<FNumericProperty>(Prop))
		{
			if (const UEnum* ByteEnum = Numeric->GetIntPropertyEnum())
			{
				return MakeShared<FJsonValueString>(
					ByteEnum->GetNameStringByValue(Numeric->GetSignedIntPropertyValue(Ptr)));
			}
			if (Numeric->IsFloatingPoint())
			{
				return Num(Numeric->GetFloatingPointPropertyValue(Ptr));
			}
			return Num(static_cast<double>(Numeric->GetSignedIntPropertyValue(Ptr)));
		}
		if (const FStructProperty* Struct = CastField<FStructProperty>(Prop))
		{
			if (Struct->Struct == TBaseStructure<FVector>::Get())
			{
				return Vec(*static_cast<const FVector*>(Ptr));
			}
			if (Struct->Struct == TBaseStructure<FRotator>::Get())
			{
				return Rot(*static_cast<const FRotator*>(Ptr));
			}
		}
		if (const FNameProperty* Name = CastField<FNameProperty>(Prop))
		{
			return MakeShared<FJsonValueString>(Name->GetPropertyValue(Ptr).ToString());
		}
		if (const FStrProperty* Str = CastField<FStrProperty>(Prop))
		{
			return MakeShared<FJsonValueString>(Str->GetPropertyValue(Ptr));
		}
		FString Text;
		Prop->ExportTextItem_Direct(Text, Ptr, nullptr, nullptr, PPF_None);
		return MakeShared<FJsonValueString>(Text);
	}

	/** A property, or a const/pure parameterless function, so reading cannot change state. */
	static TSharedPtr<FJsonValue> ReadValue(UObject* Object, FName Name)
	{
		if (!Object)
		{
			return Null();
		}
		if (const FProperty* Prop = Object->GetClass()->FindPropertyByName(Name))
		{
			return PropertyValue(Prop, Prop->ContainerPtrToValuePtr<void>(Object));
		}
		UFunction* Function = Object->FindFunction(Name);
		const FProperty* Return = Function ? Function->GetReturnProperty() : nullptr;
		if (Return && Function->NumParms == 1 && Function->HasAnyFunctionFlags(FUNC_Const | FUNC_BlueprintPure))
		{
			uint8* Params = static_cast<uint8*>(FMemory_Alloca(Function->ParmsSize));
			Function->InitializeStruct(Params);
			Object->ProcessEvent(Function, Params);
			TSharedPtr<FJsonValue> Value = PropertyValue(Return, Return->ContainerPtrToValuePtr<void>(Params));
			Function->DestroyStruct(Params);
			return Value;
		}
		return Null();
	}
}

UKilnProbeComponent::UKilnProbeComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;
	PrimaryComponentTick.TickGroup = TG_PostPhysics; // after the physics step of this frame
	bTickInEditor = false;
}

void UKilnProbeComponent::BeginPlay()
{
	Super::BeginPlay();
	if (bStartOnBeginPlay)
	{
		StartRecording(Task, FString());
	}
}

void UKilnProbeComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	StopRecording();
	Super::EndPlay(EndPlayReason);
}

FString UKilnProbeComponent::StartRecording(const FString& InTask, const FString& RunName)
{
	if (bRecording)
	{
		StopRecording();
	}
	if (!InTask.IsEmpty())
	{
		Task = InTask;
	}
	const FString Run = RunName.IsEmpty() ? FDateTime::UtcNow().ToString(TEXT("%Y%m%d-%H%M%S")) : RunName;
	const AActor* Owner = GetOwner();
	const FString OwnerName = Owner ? KilnProbe::LabelOf(Owner) : FString(TEXT("probe"));
	OutputFile = FPaths::ConvertRelativePathToFull(
		FPaths::ProjectSavedDir() / TEXT("Kiln") / TEXT("Probes") / KilnProbe::Safe(Task)
		/ FString::Printf(TEXT("%s_%s.jsonl"), *KilnProbe::Safe(Run), *KilnProbe::Safe(OwnerName)));
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputFile), true);

	const UWorld* World = GetWorld();
	StartTime = World ? World->GetTimeSeconds() : 0.0;
	NextSampleTime = StartTime;
	SampleIndex = 0;
	FrameCount = 0;
	Pending.Reset();
	bFileCreated = false;
	bRecording = true;
	WriteHeader(Run);
	Flush();
	SetComponentTickEnabled(true);
	return OutputFile;
}

FString UKilnProbeComponent::StopRecording()
{
	if (!bRecording)
	{
		return OutputFile;
	}
	const TSharedRef<FJsonObject> End = MakeShared<FJsonObject>();
	End->SetStringField(TEXT("type"), TEXT("end"));
	End->SetNumberField(TEXT("samples"), SampleIndex);
	End->SetNumberField(TEXT("frames"), FrameCount);
	AppendLine(End);
	Flush();
	bRecording = false;
	SetComponentTickEnabled(false);
	return OutputFile;
}

void UKilnProbeComponent::TickComponent(float DeltaTime, ELevelTick TickType,
	FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (!bRecording)
	{
		return;
	}
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;
	const bool bDue = SampleHz <= 0.f || Now + 1e-6 >= NextSampleTime;
	if (!bDue && !bRecordFrameTiming)
	{
		return;
	}

	const TSharedRef<FJsonObject> Line = MakeShared<FJsonObject>();
	if (bDue)
	{
		Line->SetStringField(TEXT("type"), TEXT("tick"));
		Line->SetNumberField(TEXT("tick"), ++SampleIndex);
		Line->SetField(TEXT("t"), KilnProbe::Num(Now - StartTime));
		WriteChannels(*Line);
		if (SampleHz > 0.f)
		{
			const double Interval = 1.0 / SampleHz;
			NextSampleTime = NextSampleTime + Interval > Now ? NextSampleTime + Interval : Now + Interval;
		}
	}
	else
	{
		Line->SetStringField(TEXT("type"), TEXT("frame"));
	}
	if (bRecordFrameTiming)
	{
		WriteFrameTiming(*Line);
		++FrameCount;
	}
	AppendLine(Line);

	if (bDue && SampleLimit > 0 && SampleIndex >= SampleLimit)
	{
		StopRecording();
	}
}

void UKilnProbeComponent::WriteHeader(const FString& RunName)
{
	const UWorld* World = GetWorld();
	const TSharedRef<FJsonObject> Header = MakeShared<FJsonObject>();
	Header->SetStringField(TEXT("type"), TEXT("header"));
	Header->SetStringField(TEXT("format"), TEXT("kiln-probe/1"));
	Header->SetStringField(TEXT("engine"), TEXT("unreal"));
	Header->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());
	Header->SetStringField(TEXT("task"), Task);
	Header->SetStringField(TEXT("run"), RunName);
	Header->SetStringField(TEXT("map"), World ? World->GetMapName() : FString());
	Header->SetStringField(TEXT("owner"), GetOwner() ? KilnProbe::LabelOf(GetOwner()) : FString());
	Header->SetStringField(TEXT("sample"), TEXT("post_physics"));
	Header->SetNumberField(TEXT("sample_hz"), SampleHz);
	Header->SetNumberField(TEXT("units_per_meter"), 100.0);
	Header->SetStringField(TEXT("up"), TEXT("z"));
	if (World && World->GetWorldSettings())
	{
		Header->SetNumberField(TEXT("time_dilation"), World->GetWorldSettings()->GetEffectiveTimeDilation());
	}
	Header->SetBoolField(TEXT("fixed_timestep"), FApp::UseFixedTimeStep());
	Header->SetStringField(TEXT("started_utc"), FDateTime::UtcNow().ToIso8601());
	AppendLine(Header);
}

void UKilnProbeComponent::WriteChannels(FJsonObject& Line) const
{
	AActor* Owner = GetOwner();
	if (bRecordOwner && Owner)
	{
		const FString Prefix = KilnProbe::LabelOf(Owner);
		Line.SetField(Prefix + TEXT(".pos"), KilnProbe::Vec(Owner->GetActorLocation()));
		Line.SetField(Prefix + TEXT(".vel"), KilnProbe::Vec(Owner->GetVelocity()));
		if (const ACharacter* Character = Cast<ACharacter>(Owner))
		{
			if (const UCharacterMovementComponent* Movement = Character->GetCharacterMovement())
			{
				Line.SetStringField(Prefix + TEXT(".mode"), Movement->GetMovementName());
				Line.SetBoolField(Prefix + TEXT(".grounded"), Movement->IsMovingOnGround());
			}
		}
	}
	for (const FKilnProbeActor& Entry : Actors)
	{
		const AActor* Actor = Entry.Actor.Get();
		if (!Actor)
		{
			continue;
		}
		const FString Prefix = Entry.Label.IsEmpty() ? KilnProbe::LabelOf(Actor) : Entry.Label;
		Line.SetField(Prefix + TEXT(".pos"), KilnProbe::Vec(Actor->GetActorLocation()));
		if (Entry.bVelocity)
		{
			Line.SetField(Prefix + TEXT(".vel"), KilnProbe::Vec(Actor->GetVelocity()));
		}
		if (Entry.bRotation)
		{
			Line.SetField(Prefix + TEXT(".rot"), KilnProbe::Rot(Actor->GetActorRotation()));
		}
	}
	for (const FKilnProbeSocket& Entry : Sockets)
	{
		const FString Name = Entry.Label.IsEmpty() ? Entry.Socket.ToString() : Entry.Label;
		const AActor* Actor = KilnProbe::Resolve(Entry.Actor, Owner);
		const USceneComponent* Component = nullptr;
		if (Actor && Entry.Component.IsNone())
		{
			Component = Actor->FindComponentByClass<USkeletalMeshComponent>();
			Component = Component ? Component : Actor->GetRootComponent();
		}
		else if (Actor)
		{
			Component = Cast<USceneComponent>(KilnProbe::FindComponent(Actor, Entry.Component));
		}
		Line.SetField(Name, Component ? KilnProbe::Vec(Component->GetSocketLocation(Entry.Socket))
		                              : KilnProbe::Null());
	}
	for (const FKilnProbeValue& Entry : Values)
	{
		const FString Name = Entry.Label.IsEmpty() ? Entry.Name.ToString() : Entry.Label;
		AActor* Actor = KilnProbe::Resolve(Entry.Actor, Owner);
		UObject* Target = Actor;
		if (Actor && !Entry.Component.IsNone())
		{
			Target = KilnProbe::FindComponent(Actor, Entry.Component);
		}
		Line.SetField(Name, KilnProbe::ReadValue(Target, Entry.Name));
	}
}

void UKilnProbeComponent::WriteFrameTiming(FJsonObject& Line) const
{
	// Thread and GPU times are the engine's stat-unit values in cycles; they describe recent
	// frames (the render thread and GPU run behind the game thread).
	Line.SetNumberField(TEXT("frame"), static_cast<double>(GFrameCounter));
	Line.SetField(TEXT("dt_ms"), KilnProbe::Num(FApp::GetDeltaTime() * 1000.0));
	Line.SetField(TEXT("game_ms"), KilnProbe::Num(FPlatformTime::ToMilliseconds(GGameThreadTime)));
	Line.SetField(TEXT("render_ms"), KilnProbe::Num(FPlatformTime::ToMilliseconds(GRenderThreadTime)));
	const uint32 GpuCycles = GDynamicRHI ? RHIGetGPUFrameCycles(0) : 0;
	Line.SetField(TEXT("gpu_ms"), KilnProbe::Num(FPlatformTime::ToMilliseconds(GpuCycles)));
}

void UKilnProbeComponent::AppendLine(const TSharedRef<FJsonObject>& Line)
{
	FString Text;
	const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
		TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
	FJsonSerializer::Serialize(Line, Writer);
	Pending += Text;
	Pending += TEXT("\n");
	if (Pending.Len() > 64 * 1024 || FPlatformTime::Seconds() - LastFlush > 1.0)
	{
		Flush();
	}
}

void UKilnProbeComponent::Flush()
{
	if (Pending.IsEmpty() || OutputFile.IsEmpty())
	{
		return;
	}
	// First write truncates a file left by an earlier run with the same name; later writes append.
	FFileHelper::SaveStringToFile(Pending, *OutputFile, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
		&IFileManager::Get(), bFileCreated ? FILEWRITE_Append : FILEWRITE_None);
	bFileCreated = true;
	Pending.Reset();
	LastFlush = FPlatformTime::Seconds();
}
