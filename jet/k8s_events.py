# List of event names from https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/events/event.go

K8S_EVENTS = [
    # Container events
    "Created",
    "Started",
    "Failed",  # covers FailedToCreateContainer, FailedToStartContainer, FailedToPullImage, FailedToMakePodDataDirectories
    "Killing",
    "Preempting",
    "BackOff",  # covers BackOffStartContainer, BackOffPullImage
    "ExceededGracePeriod",
    
    # Pod events
    "FailedKillPod",
    "FailedCreatePodContainer",
    "NetworkNotReady",
    "ResizeDeferred",
    "ResizeInfeasible",
    "ResizeCompleted",
    "ResizeStarted",
    "ResizeError",
    "FailedNodeDeclaredFeaturesCheck",
    
    # Image events
    "Pulling",
    "Pulled",
    "InspectFailed",
    "ErrImageNeverPull",
    
    # Kubelet/Node events
    "NodeReady",
    "NodeNotReady",
    "NodeSchedulable",
    "NodeNotSchedulable",
    "Starting",
    "KubeletSetupFailed",
    "FailedAttachVolume",
    "FailedMount",  
    "VolumeResizeFailed",
    "VolumeResizeSuccessful",
    "FileSystemResizeFailed",
    "VolumePermissionChangeInProgress",
    "FileSystemResizeSuccessful",
    "FailedMapVolume",
    "AlreadyMountedVolume",
    "SuccessfulAttachVolume",
    "SuccessfulMountVolume",
    "Rebooted",
    "Shutdown",
    "ContainerGCFailed",
    "ImageGCFailed",
    "FailedNodeAllocatableEnforcement",
    "NodeAllocatableEnforced",
    "SandboxChanged",
    "FailedCreatePodSandBox",
    "FailedPodSandBoxStatus",
    "FailedMountOnFilesystemMismatch",
    "FailedPrepareDynamicResources",
    "PossibleMemoryBackedVolumesOnDisk",
    "CgroupV1",
    
    # Image manager events
    "InvalidDiskCapacity",
    "FreeDiskSpaceFailed",
    
    # Probe events
    "Unhealthy",  
    "ProbeWarning",
    
    # Pod worker events
    "FailedSync",
    
    # Config events
    "FailedValidation",
    
    # Lifecycle hooks
    "FailedPostStartHook",
    "FailedPreStopHook",
    
    # Scheduler events (not in kubelet)
    "Scheduled",
    "FailedScheduling",
    "Preempted",
    
    # Controller events (not in kubelet)
    "SuccessfulCreate",
    "SuccessfulDelete",
    "ScalingReplicaSet",

    # KAI-scheduler events (not in kubelet)
    "Unschedulable",
    "FailedBinding",
    # "PodGrouperWarning", # noisy

    # Controller events
    "FailedCreate",
    "FailedDelete",
    "SuccessfulCreate",
    "SuccessfulDelete",


]